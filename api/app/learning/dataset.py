"""The dataset (Component 12). One row per company per week, built from what every other
component already wrote: the plan (settings), the scorecard (channel state), the outcome
row (results), the ICP embedding (for neighbours). Built on Friday close, after the
outcome row; rebuilt idempotently."""
from datetime import date, timedelta

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ..models import ICP, Company, CompanyWeek, ExperimentArm, Outcome, Plan

FEATURE_VERSION = "feat-v1"


def _icp_vec(db: Session, company_id) -> list[float] | None:
    v = db.execute(text("SELECT embedding::text FROM icp WHERE company_id = :c ORDER BY version DESC LIMIT 1"), {"c": str(company_id)}).scalar()
    return [float(x) for x in v.strip("[]").split(",")] if v else None


def build_week(db: Session, company: Company, week_start: date) -> CompanyWeek | None:
    outcome = db.scalars(select(Outcome).where(Outcome.company_id == company.id, Outcome.week_start == week_start)).first()
    plan = db.scalars(select(Plan).where(Plan.company_id == company.id, Plan.week_start <= week_start).order_by(Plan.week_start.desc())).first()
    if not outcome or not plan:
        return None
    prev = db.scalars(select(Outcome).where(Outcome.company_id == company.id, Outcome.week_start == week_start - timedelta(days=7))).first()
    sc = plan.scorecard or {}
    weekly = (sc.get("weekly") or {})
    settings = weekly.get("settings") or {}
    arm_row = db.get(ExperimentArm, company.id)
    icp = db.scalars(select(ICP).where(ICP.company_id == company.id).order_by(ICP.version.desc())).first()

    channel_scores = {k: v.get("score") for k, v in sc.items() if isinstance(v, dict) and "score" in v and not k.startswith("_")}
    pa = (prev.actuals if prev else {}) or {}
    a = outcome.actuals or {}
    features = {
        "version": FEATURE_VERSION,
        "stage": company.stage,
        "industry": ((icp.firmographics or {}).get("industry") or [None])[0] if icp else None,
        "week_no": ((week_start - plan.week_start).days // 7 + 1) if plan else None,
        "channel_scores": channel_scores,
        "prev_impressions_icp": pa.get("impressions_icp"),
        "prev_approval_rate": pa.get("approval_rate"),
        "prev_edit_rate": pa.get("edit_rate"),
        "prev_signups": pa.get("signups"),
        "focus": weekly.get("focus"),
        "rules": [d.get("rule") for d in weekly.get("decisions", [])],
    }
    result = {
        "impressions_icp": a.get("impressions_icp"),
        "delta_wow": (a.get("impressions_icp") or 0) - (pa.get("impressions_icp") or 0) if pa else None,
        "growth_wow": ((a.get("impressions_icp") or 0) / pa["impressions_icp"] - 1) if pa.get("impressions_icp") else None,
        "approval_rate": a.get("approval_rate"),
        "edit_rate": a.get("edit_rate"),
        "signups": a.get("signups"),
    }
    row = db.scalars(select(CompanyWeek).where(CompanyWeek.company_id == company.id, CompanyWeek.week_start == week_start)).first()
    if not row:
        row = CompanyWeek(company_id=company.id, week_start=week_start)
        db.add(row)
    row.arm = arm_row.arm if arm_row else "rules"
    row.features, row.settings, row.result = features, settings, result
    db.flush()
    vec = _icp_vec(db, company.id)
    if vec:
        db.execute(text("UPDATE company_week SET embedding = :v WHERE id = :id"), {"v": str(vec), "id": str(row.id)})
    db.commit()
    db.refresh(row)
    return row


def build_all(db: Session, week_start: date) -> int:
    n = 0
    for c in db.scalars(select(Company).where(Company.status == "active")):
        if build_week(db, c, week_start):
            n += 1
    return n


def size(db: Session) -> dict:
    rows = db.scalars(select(CompanyWeek)).all()
    companies = {r.company_id for r in rows}
    with_result = [r for r in rows if r.result.get("growth_wow") is not None]
    return {"rows": len(rows), "companies": len(companies), "rows_with_growth": len(with_result),
            "ready_for_learning": len(companies) >= 100 and len(with_result) >= 800}
