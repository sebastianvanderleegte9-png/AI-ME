"""Joint launches (Component 9, v1): the product brokers launches between companies on it.

match:   for company A, every other active company B where
           - ICPs are adjacent (embedding similarity in a band: not identical, not unrelated)
           - products don't compete (product summaries dissimilar; no shared competitor list overlap with each other)
           - B has a launch-ready proof point or an open feature drop
         score = 0.5*adjacency + 0.3*non_compete + 0.2*readiness
propose: one relationship row visible to both founders, with a suggested hook.
accept:  each founder taps; when both have, a joint launch is created for each company
         (playbook joint-v1) and linked in relationship.plan."""
from datetime import date, datetime, timezone
import json
import uuid

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ..interfaces import get_llm
from ..launch.kit import create_launch, expand, propose_date
from ..models import ICP, Company, Founder, Relationship

ADJ_LO, ADJ_HI = 0.25, 0.85     # ICP similarity band for "adjacent"
COMPETE_MAX = 0.75              # product similarity above this = competitors, skip

HOOK_SYS = """Two non-competing B2B companies with adjacent customers are planning a joint launch.
Given both product summaries and ICPs, write ONE sentence both founders could say (the joint hook),
and one line each on what each company brings. Return JSON: {"hook": "...", "brings": {"a": "...", "b": "..."}}"""


def _cos(a, b):
    return sum(x * y for x, y in zip(a, b))


def _vec(db: Session, table: str, id_: uuid.UUID) -> list[float] | None:
    v = db.execute(text(f"SELECT embedding::text FROM {table} WHERE id = :id"), {"id": str(id_)}).scalar()
    if not v:
        return None
    return [float(x) for x in v.strip("[]").split(",")]


def _latest_icp(db: Session, company_id: uuid.UUID) -> ICP | None:
    return db.scalars(select(ICP).where(ICP.company_id == company_id).order_by(ICP.version.desc())).first()


def _summary(c: Company) -> dict:
    try:
        return json.loads(c.product_summary or "{}") or {}
    except json.JSONDecodeError:
        return {}


def match(db: Session, company: Company, limit: int = 5) -> list[dict]:
    llm = get_llm()
    my_icp = _latest_icp(db, company.id)
    if not my_icp:
        return []
    my_icp_v = _vec(db, "icp", my_icp.id)
    my_sum = _summary(company)
    my_prod_v = llm.embed([json.dumps(my_sum)], purpose="joint_match")[0]
    my_comp = {c.lower() for c in my_sum.get("competitors_mentioned", [])}
    existing = {r.partner_company_id for r in db.scalars(select(Relationship).where(
        Relationship.company_id == company.id, Relationship.kind == "joint_launch",
        Relationship.state.not_in(["declined", "cancelled", "done"])))}

    out = []
    for other in db.scalars(select(Company).where(Company.id != company.id, Company.status == "active")):
        if other.id in existing:
            continue
        o_icp = _latest_icp(db, other.id)
        if not o_icp or not my_icp_v:
            continue
        o_icp_v = _vec(db, "icp", o_icp.id)
        if not o_icp_v:
            continue
        adj = _cos(my_icp_v, o_icp_v)
        if not (ADJ_LO <= adj <= ADJ_HI):
            continue
        o_sum = _summary(other)
        prod_sim = _cos(my_prod_v, llm.embed([json.dumps(o_sum)], purpose="joint_match")[0])
        o_comp = {c.lower() for c in o_sum.get("competitors_mentioned", [])}
        competes = prod_sim > COMPETE_MAX or other.name.lower() in my_comp or company.name.lower() in o_comp
        if competes:
            continue
        readiness = 1.0 if o_sum.get("proof_points") else 0.5
        score = round(0.5 * adj + 0.3 * (1 - prod_sim) + 0.2 * readiness, 3)
        out.append({"company_id": str(other.id), "name": other.name, "score": score, "icp_adjacency": round(adj, 3),
                    "product_similarity": round(prod_sim, 3), "readiness": readiness,
                    "reason": f"ICPs adjacent ({adj:.2f}), products distinct ({prod_sim:.2f}), {'has proof points' if readiness == 1 else 'no proof yet'}"})
    out.sort(key=lambda x: -x["score"])
    return out[:limit]


def propose(db: Session, company: Company, partner: Company, score: float, reason: str) -> Relationship:
    llm = get_llm()
    a, b = _summary(company), _summary(partner)
    ia, ib = _latest_icp(db, company.id), _latest_icp(db, partner.id)
    raw = llm.complete(HOOK_SYS, json.dumps({"a": {"name": company.name, "product": a, "icp": ia.description if ia else None},
                                             "b": {"name": partner.name, "product": b, "icp": ib.description if ib else None}}),
                       purpose="joint_hook", json_mode=True, max_tokens=300).text
    try:
        hook = json.loads(raw)
        if hook.get("fake"):
            raise ValueError
    except (json.JSONDecodeError, ValueError):
        hook = {"hook": f"{company.name} and {partner.name} serve the same buyers from two sides; together the workflow is complete.",
                "brings": {"a": a.get("one_liner") or company.name, "b": b.get("one_liner") or partner.name}}
    r = Relationship(company_id=company.id, kind="joint_launch", partner_company_id=partner.id, state="proposed",
                     score=score, reason=reason, plan={"hook": hook.get("hook"), "brings": hook.get("brings", {}),
                                                        "proposed_date": str(propose_date("joint"))},
                     log=[{"at": datetime.now(timezone.utc).isoformat(), "event": "proposed", "detail": reason}])
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def decide(db: Session, rel: Relationship, company: Company, accept: bool) -> Relationship:
    """A founder's tap. Both must accept; then both launches are created."""
    now = datetime.now(timezone.utc).isoformat()
    log = list(rel.log or [])
    if not accept:
        rel.state = "declined"
        log.append({"at": now, "event": "declined", "detail": company.name})
        rel.log = log
        db.commit()
        return rel
    side = "us" if company.id == rel.company_id else "them"
    accepted = set((rel.plan or {}).get("accepted_by", []))
    accepted.add(side)
    plan = dict(rel.plan or {})
    plan["accepted_by"] = sorted(accepted)
    log.append({"at": now, "event": "accepted", "detail": company.name})
    if accepted == {"us", "them"}:
        a, b = db.get(Company, rel.company_id), db.get(Company, rel.partner_company_id)
        fa = db.scalars(select(Founder).where(Founder.company_id == a.id)).first()
        fb = db.scalars(select(Founder).where(Founder.company_id == b.id)).first()
        ld = date.fromisoformat(plan["proposed_date"])
        brief = {"what": plan.get("hook"), "why_now": plan.get("hook"), "hook": plan.get("hook"),
                 "proof": [], "partner": None, "target_signups": 100}
        La = create_launch(db, a, fa, "joint", f"Joint launch with {b.name}", ld, {**brief, "partner": b.name, "customer": b.name})
        Lb = create_launch(db, b, fb, "joint", f"Joint launch with {a.name}", ld, {**brief, "partner": a.name, "customer": a.name})
        expand(db, La)
        expand(db, Lb)
        plan["launch_id_us"], plan["launch_id_them"] = str(La.id), str(Lb.id)
        rel.state = "active"
        log.append({"at": now, "event": "launches_created", "detail": f"{La.id} / {Lb.id} on {ld}"})
    else:
        rel.state = "accepted_by_us" if side == "us" else "accepted"
    rel.plan, rel.log = plan, log
    db.commit()
    db.refresh(rel)
    return rel
