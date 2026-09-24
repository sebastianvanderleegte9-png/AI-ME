"""Sequencer (Judgment v1) — the Monday re-plan.

Reads: last week's outcome row, the standing 90-day sequence from the scorecard,
per-format approval rates, the calendar. Writes: this week's plan row with a concrete
`weekly` block (slots per platform, format weights, reply count, page batch?, launch
tasks?) and the Jobs that need creating now. Every decision carries a rule id and a
one-line reason, so the founder (and the future learned model) can see why.

Rules are versioned. A human override on any decision is logged as a labeled example
on the plan row (`overrides`), which is training data for Component 12."""
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Company, Job, Outcome, Plan
from .rules import RULES_VERSION as SCORECARD_RULES

SEQUENCER_VERSION = "seq-v1.0"

DEFAULTS = {"posts_per_platform": 5, "replies_per_platform": 5, "platforms": ["linkedin", "x"],
            "format_weights": {}, "page_batch": 0, "launch_tasks": False, "interview": True}


@dataclass
class Decision:
    rule: str
    change: dict
    reason: str


@dataclass
class WeeklyPlan:
    week_start: date
    settings: dict
    decisions: list[Decision] = field(default_factory=list)
    focus: str = ""


def _format_rates(db: Session, company_id) -> dict[str, dict]:
    rows = db.execute(select(Job.format, Job.state, func.count()).where(
        Job.company_id == company_id, Job.type == "post").group_by(Job.format, Job.state)).all()
    out: dict[str, dict] = {}
    for fmt, st, n in rows:
        d = out.setdefault(fmt, {"ok": 0, "rejected": 0, "edited": 0})
        if st == "rejected":
            d["rejected"] += n
        elif st in ("approved", "edited", "executed"):
            d["ok"] += n
            if st == "edited":
                d["edited"] += n
    for d in out.values():
        dec = d["ok"] + d["rejected"]
        d["approval"] = d["ok"] / dec if dec else None
        d["decided"] = dec
    return out


def _icp_by_format(db: Session, company_id, since: date) -> dict[str, float]:
    from ..models import Metric
    rows = db.execute(select(Job.format, func.sum(Metric.value)).join(Metric, Metric.job_id == Job.id).where(
        Job.company_id == company_id, Metric.name == "impressions_icp", Metric.date >= since).group_by(Job.format)).all()
    return {f: float(v) for f, v in rows}


def plan_week(db: Session, company: Company, week_start: date | None = None) -> WeeklyPlan:
    ws = week_start or (date.today() - timedelta(days=date.today().weekday()))
    prev_ws = ws - timedelta(days=7)
    prev = db.scalars(select(Outcome).where(Outcome.company_id == company.id, Outcome.week_start == prev_ws)).first()
    prev2 = db.scalars(select(Outcome).where(Outcome.company_id == company.id, Outcome.week_start == prev_ws - timedelta(days=7))).first()
    standing = db.scalars(select(Plan).where(Plan.company_id == company.id, Plan.sequence != []).order_by(Plan.week_start.desc())).first()
    seq = (standing.sequence if standing else []) or []
    week_no = ((ws - standing.week_start).days // 7 + 1) if standing else 1

    s = {**DEFAULTS, "format_weights": {}}
    wp = WeeklyPlan(week_start=ws, settings=s)
    D = wp.decisions.append

    # R1: which channels are 'in phase' this week per the standing 90-day sequence
    active = [x["channel"] for x in seq if x["start_week"] <= week_no <= x["end_week"]] or [x["channel"] for x in seq[:2]]
    wp.focus = ", ".join(active)
    D(Decision("R1.phase", {"active_channels": active, "week_no": week_no}, f"Week {week_no} of the 90-day sequence; in-phase channels: {', '.join(active)}."))

    # R2: attribution first — if the signup field is still missing, keep it as the top task
    if any(x["channel"] == "onboarding" and x["fix_id"] == "signup_source_field" for x in seq) and week_no <= 2:
        s["tasks"] = ["install signup-source widget"]
        D(Decision("R2.attribution", {"tasks": s["tasks"]}, "No attribution yet; installing the signup field precedes everything measurable."))

    rates = _format_rates(db, company.id)
    icp_by_fmt = _icp_by_format(db, company.id, prev_ws)

    if prev:
        a = prev.actuals or {}
        appr = a.get("approval_rate")
        edit = a.get("edit_rate")
        icp = a.get("impressions_icp", 0)
        icp2 = (prev2.actuals or {}).get("impressions_icp", 0) if prev2 else None

        # R3: approval below gate -> fewer, better; bias to the founder's best formats
        if appr is not None and appr < 0.7:
            s["posts_per_platform"] = max(3, DEFAULTS["posts_per_platform"] - 2)
            best = sorted((f for f, d in rates.items() if d["decided"] >= 3 and d["approval"] is not None), key=lambda f: -rates[f]["approval"])[:4]
            s["format_weights"] = {f: 2.0 for f in best}
            D(Decision("R3.approval_gate", {"posts_per_platform": s["posts_per_platform"], "format_weights": s["format_weights"]},
                       f"Approval {appr:.0%} is under the 70% gate; cutting volume and weighting the formats this founder approves."))
        # R4: high edit rate -> voice profile needs retraining before more volume
        if edit is not None and edit > 0.2:
            s["retrain_voice"] = True
            D(Decision("R4.edit_rate", {"retrain_voice": True}, f"Edit rate {edit:.0%} exceeds 20%; retrain the voice profile on this week's edits before drafting."))
        # R5: ICP impressions flat two weeks running with healthy approval -> shift slots toward top ICP formats and add replies
        if icp2 is not None and icp2 > 0 and icp < icp2 * 1.1 and (appr or 0) >= 0.7:
            top = sorted(icp_by_fmt, key=lambda f: -icp_by_fmt[f])[:3]
            for f in top:
                s["format_weights"][f] = s["format_weights"].get(f, 1.0) + 1.0
            s["replies_per_platform"] = min(10, DEFAULTS["replies_per_platform"] + 3)
            D(Decision("R5.plateau", {"format_weights": s["format_weights"], "replies_per_platform": s["replies_per_platform"]},
                       f"Impressions in ICP grew <10% for two weeks ({icp2:,.0f} -> {icp:,.0f}); shifting to the formats that reached the ICP and adding replies."))
        # R6: ICP impressions up >50% -> hold the mix, don't touch what works
        if icp2 and icp >= icp2 * 1.5:
            D(Decision("R6.momentum", {}, f"Impressions in ICP up {icp / icp2 - 1:.0%} week over week; holding the current mix."))

    # R7: search in phase and the company has data assets -> schedule a page batch
    if "search" in active:
        import json
        try:
            assets = (json.loads(company.product_summary or "{}") or {}).get("data_assets", [])
        except json.JSONDecodeError:
            assets = []
        if assets:
            s["page_batch"] = 30
            D(Decision("R7.page_batch", {"page_batch": 30}, f"Search is in phase and {len(assets)} data asset(s) exist; generating the first 30-page batch."))
        else:
            D(Decision("R7.no_data", {}, "Search is in phase but no data asset is identified; ask the founder for one before generating pages."))

    # R8: launches in phase -> open a launch calendar (Component 8 consumes this flag)
    if "launches" in active:
        s["launch_tasks"] = True
        D(Decision("R8.launch", {"launch_tasks": True}, "Launches are in phase; the launch kit will propose a date and calendar."))

    return wp


def commit_week(db: Session, company: Company, wp: WeeklyPlan) -> Plan:
    plan = db.scalars(select(Plan).where(Plan.company_id == company.id, Plan.week_start == wp.week_start)).first()
    if not plan:
        plan = Plan(company_id=company.id, week_start=wp.week_start, generated_by="rules")
        db.add(plan)
    sc = dict(plan.scorecard or {})
    sc["weekly"] = {"settings": wp.settings, "focus": wp.focus, "sequencer_version": SEQUENCER_VERSION,
                    "decisions": [d.__dict__ for d in wp.decisions]}
    plan.scorecard = sc
    plan.generated_by = "rules"
    plan.rules_version = f"{SCORECARD_RULES}+{SEQUENCER_VERSION}"
    if not plan.targets:
        standing = db.scalars(select(Plan).where(Plan.company_id == company.id, Plan.targets != {}).order_by(Plan.week_start.desc())).first()
        plan.targets = dict(standing.targets) if standing else {}
    db.commit()
    db.refresh(plan)
    return plan


def override(db: Session, plan: Plan, changes: dict, reason: str, by: str) -> Plan:
    """A human changes a decision. The override is applied AND logged as a labeled example."""
    sc = dict(plan.scorecard or {})
    weekly = dict(sc.get("weekly") or {})
    before = dict(weekly.get("settings") or {})
    weekly["settings"] = {**before, **changes}
    log = list(weekly.get("overrides") or [])
    log.append({"by": by, "reason": reason, "before": {k: before.get(k) for k in changes}, "after": changes})
    weekly["overrides"] = log
    sc["weekly"] = weekly
    plan.scorecard = sc
    plan.generated_by = "human"
    db.commit()
    db.refresh(plan)
    return plan
