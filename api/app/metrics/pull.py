"""Metrics pull (Component 5). Runs daily per company.

For every executed post/reply in the last 28 days: fetch platform stats, store raw
metrics, and compute impressions_icp with a versioned method. Also pulls account
follower counts, search and signup numbers via MetricsSource.

impressions_icp, method v1:
  share_icp = (# engaged handles that match an attention-map account with icp_match >= ICP_MATCH_MIN)
              / (# engaged handles), when >= MIN_ENGAGED handles are visible
  else      = ICP_PRIOR (a conservative prior, recorded as such)
  impressions_icp = impressions * share_icp
The method id is stored on every row so a later v2 can be compared, never silently swapped."""
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..interfaces import get_metrics_source, get_social
from ..models import Account, Company, Founder, Job, Metric

METHOD = "computed:icp_v1"
ICP_MATCH_MIN = 0.5
MIN_ENGAGED = 5
ICP_PRIOR = 0.2
LOOKBACK_DAYS = 28


def _upsert(db: Session, company_id, job_id, d: date, name: str, value: float, source: str) -> None:
    m = db.scalars(select(Metric).where(Metric.company_id == company_id, Metric.job_id == job_id,
                                        Metric.date == d, Metric.name == name, Metric.source == source)).first()
    if m:
        m.value = value
    else:
        db.add(Metric(company_id=company_id, job_id=job_id, date=d, name=name, value=value, source=source))


def icp_share(db: Session, company_id, platform: str, engaged_handles: list[str]) -> tuple[float, str]:
    if len(engaged_handles) < MIN_ENGAGED:
        return ICP_PRIOR, "prior"
    lows = {h.lower().lstrip("@") for h in engaged_handles}
    accs = db.scalars(select(Account).where(Account.company_id == company_id, Account.platform == platform,
                                            Account.icp_match_score >= ICP_MATCH_MIN)).all()
    matched = sum(1 for a in accs if a.handle.lower().lstrip("@") in lows)
    return matched / len(lows), "observed"


def pull_company(db: Session, company: Company, today: date | None = None) -> dict:
    social, ms = get_social(), get_metrics_source()
    today = today or date.today()
    since = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    jobs = db.scalars(select(Job).where(Job.company_id == company.id, Job.state == "executed",
                                        Job.type.in_(["post", "reply"]), Job.executed_at >= since)).all()
    n_jobs, total_imp, total_icp, observed = 0, 0.0, 0.0, 0
    for j in jobs:
        try:
            st = social.stats(founder_id=str(j.founder_id), channel=j.channel, platform_ref=j.platform_ref)
        except Exception:  # noqa: BLE001
            continue
        src = f"{j.channel}_api"
        for name, val in (("impressions", st.impressions), ("reactions", st.reactions), ("comments", st.comments),
                          ("reposts", st.reposts), ("clicks", st.clicks)):
            _upsert(db, company.id, j.id, today, name, val, src)
        share, how = icp_share(db, company.id, j.channel, st.engaged_handles)
        icp = st.impressions * share
        _upsert(db, company.id, j.id, today, "impressions_icp", icp, METHOD)
        _upsert(db, company.id, j.id, today, "icp_share", share, f"{METHOD}:{how}")
        n_jobs += 1
        total_imp += st.impressions
        total_icp += icp
        observed += how == "observed"

    # account-level: followers and followers matching ICP
    for f in db.scalars(select(Founder).where(Founder.company_id == company.id)):
        for ch in ("linkedin", "x"):
            if not getattr(f, f"{ch}_handle"):
                continue
            try:
                st = social.account_stats(founder_id=str(f.id), channel=ch)
                _upsert(db, company.id, None, today, f"followers_{ch}", st.get("followers", 0), f"{ch}_api")
            except Exception:  # noqa: BLE001
                pass

    # search + signups
    for p in ms.pull(company_id=str(company.id), since=today, until=today):
        _upsert(db, company.id, None, p.date, p.name, p.value, p.source)

    db.commit()
    return {"company_id": str(company.id), "date": str(today), "jobs_measured": n_jobs,
            "impressions": total_imp, "impressions_icp": round(total_icp), "icp_share_observed_for": observed,
            "method": METHOD}
