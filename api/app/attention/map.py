"""Attention map (Component 4).

Who does the ICP actually pay attention to, and where do they reply? Built once per
company, refreshed monthly:

  seeds   = the 3 best customers' people + ICP persona titles + persona 'where they pay attention'
  expand  = enrichment search per seed query per platform
  enrich  = headline / org / role per account
  score   = ICP fit = 0.6 * embedding similarity(headline+org, ICP) + 0.4 * role match
  cluster = buyer | influencer | peer | community, by role and reach

The daily target list (targets.py) reads from this table. Public data and licensed
enrichment only; no scraping of logged-in surfaces."""
from dataclasses import dataclass
import json
import uuid

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ..interfaces import get_enrichment, get_llm
from ..models import ICP, Account, Company

MAX_ACCOUNTS = 400
BUYER_ROLE_WORDS = ("vp", "head", "director", "chief", "cxo", "ceo", "coo", "cmo", "cro", "founder", "owner", "president", "gm", "lead")
INFLUENCER_MIN_FOLLOWS = 20_000


@dataclass
class BuildResult:
    company_id: str
    icp_version: int
    seeds: list[str]
    found: int
    stored: int
    clusters: dict


def _cos(a, b):
    return sum(x * y for x, y in zip(a, b))


def _seed_queries(icp: ICP) -> list[str]:
    q: list[str] = []
    firmo = icp.firmographics or {}
    inds = firmo.get("industry") or []
    if isinstance(inds, str):
        inds = [inds]
    for p in icp.personas or []:
        if isinstance(p, dict) and p.get("title"):
            for ind in (inds[:2] or [""]):
                q.append(f"{p['title']} {ind}".strip())
    for c in icp.best_customers or []:
        if c.get("company"):
            q.append(f"{c.get('role') or 'leadership'} {c['company']}")
    if not q and icp.description:
        q.append(icp.description[:80])
    # dedupe, keep order
    seen, out = set(), []
    for s in q:
        if s.lower() not in seen:
            seen.add(s.lower())
            out.append(s)
    return out[:12]


def _role_match(headline: str | None, role: str | None, personas: list) -> float:
    h = f"{headline or ''} {role or ''}".lower()
    titles = [str(p.get("title", "")).lower() for p in personas if isinstance(p, dict)]
    if any(t and t in h for t in titles):
        return 1.0
    if any(w in h for w in BUYER_ROLE_WORDS):
        return 0.6
    return 0.2


def _cluster(role_match: float, follows: int | None, headline: str | None) -> str:
    h = (headline or "").lower()
    if any(w in h for w in ("community", "newsletter", "podcast", "host", "curator")):
        return "community"
    if (follows or 0) >= INFLUENCER_MIN_FOLLOWS:
        return "influencer"
    if role_match >= 0.6:
        return "buyer"
    return "peer"


def build_map(db: Session, company: Company, platforms: list[str] = ("linkedin", "x")) -> BuildResult:
    enrich, llm = get_enrichment(), get_llm()
    icp = db.scalars(select(ICP).where(ICP.company_id == company.id).order_by(ICP.version.desc())).first()
    if not icp:
        raise ValueError("no ICP; run intake first")
    seeds = _seed_queries(icp)
    personas = icp.personas or []
    icp_text = f"{icp.description or ''} {json.dumps(icp.firmographics or {})}"
    icp_vec = llm.embed([icp_text], purpose="attention_icp")[0]

    found: dict[tuple[str, str], dict] = {}
    for platform in platforms:
        for s in seeds:
            for p in enrich.search_people(s, platform, limit=40):
                key = (platform, p.handle.lower())
                if key in found or len(found) >= MAX_ACCOUNTS:
                    continue
                found[key] = {"platform": platform, "handle": p.handle, "name": p.name, "headline": p.headline,
                              "org": p.org, "role": p.role, "follows_count": p.follows_count}

    if not found:
        return BuildResult(str(company.id), icp.version, seeds, 0, 0, {})

    rows = list(found.values())
    vecs = llm.embed([f"{r['headline'] or ''} {r['org'] or ''} {r['role'] or ''}" for r in rows], purpose="attention_accounts")
    clusters: dict[str, int] = {}
    stored = 0
    for r, v in zip(rows, vecs):
        sim = max(0.0, _cos(icp_vec, v))
        rm = _role_match(r["headline"], r["role"], personas)
        score = round(0.6 * sim + 0.4 * rm, 3)
        cl = _cluster(rm, r["follows_count"], r["headline"])
        clusters[cl] = clusters.get(cl, 0) + 1
        existing = db.scalars(select(Account).where(Account.company_id == company.id, Account.platform == r["platform"],
                                                    Account.handle == r["handle"])).first()
        if existing:
            existing.headline, existing.org, existing.cluster = r["headline"], r["org"], cl
            existing.icp_match_score, existing.follows_count = score, r["follows_count"]
            acc = existing
        else:
            acc = Account(company_id=company.id, platform=r["platform"], handle=r["handle"], name=r["name"],
                          headline=r["headline"], org=r["org"], cluster=cl, icp_match_score=score,
                          follows_count=r["follows_count"], interaction={"icp_version": icp.version})
            db.add(acc)
        db.flush()
        db.execute(text("UPDATE account SET embedding = :v WHERE id = :id"), {"v": str(v), "id": str(acc.id)})
        stored += 1
    db.commit()
    return BuildResult(str(company.id), icp.version, seeds, len(found), stored, clusters)
