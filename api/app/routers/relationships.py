import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import require_api_key
from ..db import get_db
from ..models import Account, Company, Founder, Relationship
from ..relationships import joint, outreach

router = APIRouter(tags=["relationships"], dependencies=[Depends(require_api_key)])


class ProposeIn(BaseModel):
    partner_company_id: uuid.UUID


class DecideIn(BaseModel):
    company_id: uuid.UUID          # which founder is tapping
    accept: bool


class OutreachIn(BaseModel):
    founder_id: uuid.UUID
    account_ids: list[uuid.UUID] | None = None   # default: top candidates
    limit: int = Field(default=5, ge=1, le=10)


def _company(cid, db):
    c = db.get(Company, cid)
    if not c:
        raise HTTPException(404, "company not found")
    return c


def _out(r: Relationship, db: Session):
    d = {"id": str(r.id), "kind": r.kind, "state": r.state, "score": r.score, "reason": r.reason, "plan": r.plan, "log": r.log}
    if r.partner_company_id:
        p = db.get(Company, r.partner_company_id)
        d["partner"] = {"id": str(r.partner_company_id), "name": p.name if p else None}
    if r.account_id:
        a = db.get(Account, r.account_id)
        d["account"] = {"id": str(r.account_id), "handle": a.handle if a else None, "platform": a.platform if a else None, "cluster": a.cluster if a else None}
    return d


# ---- joint launches ----
@router.get("/companies/{company_id}/relationships/matches")
def matches(company_id: uuid.UUID, limit: int = 5, db: Session = Depends(get_db)):
    return joint.match(db, _company(company_id, db), limit)


@router.post("/companies/{company_id}/relationships/joint", status_code=201)
def propose_joint(company_id: uuid.UUID, body: ProposeIn, db: Session = Depends(get_db)):
    c = _company(company_id, db)
    p = _company(body.partner_company_id, db)
    m = next((x for x in joint.match(db, c, 50) if x["company_id"] == str(p.id)), None)
    if not m:
        raise HTTPException(422, "not a match: competing, unrelated, or already proposed")
    return _out(joint.propose(db, c, p, m["score"], m["reason"]), db)


@router.post("/relationships/{rel_id}/decide")
def decide(rel_id: uuid.UUID, body: DecideIn, db: Session = Depends(get_db)):
    r = db.get(Relationship, rel_id)
    if not r or r.kind != "joint_launch":
        raise HTTPException(404, "joint relationship not found")
    if body.company_id not in (r.company_id, r.partner_company_id):
        raise HTTPException(403, "not a party to this relationship")
    return _out(joint.decide(db, r, _company(body.company_id, db), body.accept), db)


# ---- outreach ----
@router.get("/companies/{company_id}/relationships/outreach/candidates")
def outreach_candidates(company_id: uuid.UUID, limit: int = 5, db: Session = Depends(get_db)):
    return [{"id": str(a.id), "handle": a.handle, "platform": a.platform, "cluster": a.cluster, "headline": a.headline, "fit": a.icp_match_score}
            for a in outreach.candidates(db, _company(company_id, db), limit)]


@router.post("/companies/{company_id}/relationships/outreach", status_code=201)
def start_outreach(company_id: uuid.UUID, body: OutreachIn, db: Session = Depends(get_db)):
    c = _company(company_id, db)
    f = db.get(Founder, body.founder_id)
    if not f or f.company_id != c.id:
        raise HTTPException(404, "founder not found")
    accs = [db.get(Account, i) for i in body.account_ids] if body.account_ids else outreach.candidates(db, c, body.limit)
    out = []
    for a in accs:
        if a and a.company_id == c.id:
            try:
                out.append(_out(outreach.start(db, c, f, a), db))
            except ValueError as e:
                raise HTTPException(422, str(e))
    return out


@router.post("/relationships/{rel_id}/replied")
def replied(rel_id: uuid.UUID, note: str = "", db: Session = Depends(get_db)):
    r = db.get(Relationship, rel_id)
    if not r or r.kind != "outreach":
        raise HTTPException(404, "outreach relationship not found")
    return _out(outreach.mark_replied(db, r, note), db)


@router.get("/companies/{company_id}/relationships")
def list_rels(company_id: uuid.UUID, kind: str | None = None, db: Session = Depends(get_db)):
    q = select(Relationship).where((Relationship.company_id == company_id) | (Relationship.partner_company_id == company_id))
    if kind:
        q = q.where(Relationship.kind == kind)
    rels = db.scalars(q.order_by(Relationship.created_at.desc())).all()
    return {"relationships": [_out(r, db) for r in rels], "outreach": outreach.stats(db, _company(company_id, db))}
