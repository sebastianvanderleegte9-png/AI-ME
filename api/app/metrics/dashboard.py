"""Data for the client-facing metrics dashboard (Component 16). Reads only — everything here
is already computed by rollup()/write_outcome()/friday_close(); this just shapes it for display.
No new tables: Outcome is the weekly time series, rollup() gives the current week's live detail."""
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Company, Job, Meeting, Outcome, Plan
from .report import rollup, week_bounds

WEEKS_OF_HISTORY = 10

# Fixed categorical order for signup-source identity, validated against the navy dark surface
# (node scripts/validate_palette.js "#4f8ef7,#1fae76,#c2870f,#a855f7" --mode dark --surface "#070d1a"
#  -> ALL CHECKS PASS: lightness band, chroma floor, CVD separation >= 8, normal-vision floor >= 15,
#  contrast >= 3:1). Never reordered; a 5th source folds into "other" rather than adding a hue.
SOURCE_COLORS = {
    "linkedin": "#4f8ef7",
    "x": "#1fae76",
    "search": "#c2870f",
    "referral": "#a855f7",
}
SOURCE_FALLBACK = "#5b6b8a"   # --mute-ish, for anything past the 4 fixed slots ("other")
SOURCE_ORDER = ["linkedin", "x", "search", "referral"]


def dashboard_data(db: Session, company: Company) -> dict:
    cur_start, cur_end = week_bounds()
    r = rollup(db, company, cur_start)

    plan = db.scalars(select(Plan).where(Plan.company_id == company.id, Plan.week_start <= cur_start)
                      .order_by(Plan.week_start.desc())).first()
    growth_score = (plan.scorecard or {}).get("_overall") if plan else None

    since = cur_start - timedelta(weeks=WEEKS_OF_HISTORY - 1)
    outcomes = db.scalars(select(Outcome).where(Outcome.company_id == company.id, Outcome.week_start >= since)
                          .order_by(Outcome.week_start)).all()
    trend = [{"week_start": str(o.week_start), "impressions_icp": (o.actuals or {}).get("impressions_icp", 0),
              "signups": (o.actuals or {}).get("signups", 0)} for o in outcomes]
    # today's live week isn't in Outcome until Friday close — show it as the trailing point so the
    # chart doesn't look stale mid-week
    if not trend or trend[-1]["week_start"] != str(cur_start):
        trend.append({"week_start": str(cur_start), "impressions_icp": r["this"]["impressions_icp"],
                       "signups": r["this"]["signups"]})

    sources_raw = r["signup_sources"]
    ordered = [(k, sources_raw.get(k, 0)) for k in SOURCE_ORDER if sources_raw.get(k, 0) > 0]
    other = sum(v for k, v in sources_raw.items() if k not in SOURCE_ORDER)
    if other:
        ordered.append(("other", other))
    sources = [{"name": k, "count": v, "color": SOURCE_COLORS.get(k, SOURCE_FALLBACK)} for k, v in ordered]

    month_ago = date.today() - timedelta(days=30)
    emails_sent = db.scalar(select(func.count()).where(Job.company_id == company.id, Job.type == "outreach",
                                                        Job.channel == "email", Job.state == "executed",
                                                        Job.executed_at >= month_ago)) or 0
    meetings_confirmed = db.scalar(select(func.count()).where(Meeting.company_id == company.id, Meeting.state == "confirmed",
                                                               Meeting.updated_at >= month_ago)) or 0

    return {"week_start": r["week_start"], "week_end": r["week_end"], "this": r["this"], "prev": r["prev"],
            "delta": r["delta"], "approval_rate": r["approval_rate"], "edit_rate": r["edit_rate"],
            "growth_score": growth_score, "trend": trend, "sources": sources,
            "emails_sent_30d": emails_sent, "meetings_confirmed_30d": meetings_confirmed}
