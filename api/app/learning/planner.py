"""Learned planner (Judgment v2). Retrieval, not a black box:

  1. find the K most similar company-weeks (ICP embedding cosine, same stage bonus, similar
     channel state, similar prior approval), excluding this company's own rows
  2. among those, take the weeks with the best growth_wow and read the settings they ran
  3. propose this week's settings as the weighted median of the winners' settings
  4. every proposal carries the neighbours it came from (company, week, growth, settings)
     so a human can audit it and the rules engine can veto it

If fewer than MIN_NEIGHBOURS usable neighbours exist, the planner abstains and the rules
engine plans the week (recorded as such). The rules engine's hard constraints always apply
on top: approval gate, attribution first, voice retraining."""
from dataclasses import dataclass, field
from datetime import date
import statistics

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ..models import Company, CompanyWeek, ICP, Outcome
from ..judgment.sequencer import DEFAULTS, Decision, WeeklyPlan, plan_week

PLANNER_VERSION = "learned-v2.0"
K = 25
MIN_NEIGHBOURS = 8
TOP_FRACTION = 0.3


@dataclass
class Neighbour:
    company_id: str
    week_start: str
    similarity: float
    growth_wow: float
    settings: dict
    features: dict = field(default_factory=dict)


def _cos(a, b):
    return sum(x * y for x, y in zip(a, b))


def _vec(s: str | None):
    return [float(x) for x in s.strip("[]").split(",")] if s else None


def neighbours(db: Session, company: Company, k: int = K) -> list[Neighbour]:
    me = db.execute(text("SELECT embedding::text FROM icp WHERE company_id = :c ORDER BY version DESC LIMIT 1"), {"c": str(company.id)}).scalar()
    mv = _vec(me)
    if not mv:
        return []
    my_prev = db.scalars(select(Outcome).where(Outcome.company_id == company.id).order_by(Outcome.week_start.desc())).first()
    my_appr = (my_prev.actuals or {}).get("approval_rate") if my_prev else None
    rows = db.execute(text("""
        SELECT id, company_id, week_start, features, settings, result, embedding::text
        FROM company_week WHERE company_id <> :c AND embedding IS NOT NULL
          AND (result->>'growth_wow') IS NOT NULL"""), {"c": str(company.id)}).all()
    out = []
    for _id, cid, ws, feats, sets, res, emb in rows:
        v = _vec(emb)
        if not v:
            continue
        sim = _cos(mv, v)
        if feats.get("stage") == company.stage:
            sim += 0.05
        pa = feats.get("prev_approval_rate")
        if my_appr is not None and pa is not None:
            sim -= abs(my_appr - pa) * 0.2
        out.append(Neighbour(str(cid), str(ws), round(sim, 4), float(res["growth_wow"]), sets or {}, feats or {}))
    out.sort(key=lambda n: -n.similarity)
    return out[:k]


def _median_int(vals: list[int], default: int) -> int:
    return int(statistics.median(vals)) if vals else default


def propose(db: Session, company: Company, week_start: date | None = None) -> tuple[WeeklyPlan, list[Neighbour]]:
    """Returns the learned plan. Starts from the rules plan so hard constraints (R2, R3, R4) stay,
    then overrides the tunable settings from the winners among the neighbours."""
    base = plan_week(db, company, week_start)
    ns = neighbours(db, company)
    usable = [n for n in ns if n.settings]
    if len(usable) < MIN_NEIGHBOURS:
        base.decisions.append(Decision("L0.abstain", {}, f"Learned planner abstained: {len(usable)} usable neighbours (< {MIN_NEIGHBOURS}); rules planned this week."))
        base.settings["planner"] = "rules"
        return base, ns

    winners = sorted(usable, key=lambda n: -n.growth_wow)[: max(3, int(len(usable) * TOP_FRACTION))]
    hard = {k: base.settings[k] for k in ("retrain_voice", "tasks", "page_batch", "launch_tasks", "proposed_launch", "propose_tools") if k in base.settings}
    gated = any(d.rule.startswith("R3") for d in base.decisions)

    posts = _median_int([int(n.settings.get("posts_per_platform", DEFAULTS["posts_per_platform"])) for n in winners], DEFAULTS["posts_per_platform"])
    replies = _median_int([int(n.settings.get("replies_per_platform", DEFAULTS["replies_per_platform"])) for n in winners], DEFAULTS["replies_per_platform"])
    fw: dict[str, list[float]] = {}
    for n in winners:
        for f, w in (n.settings.get("format_weights") or {}).items():
            fw.setdefault(f, []).append(float(w))
    weights = {f: round(statistics.median(ws), 2) for f, ws in fw.items() if len(ws) >= 2}

    s = dict(base.settings)
    if not gated:                       # R3 (approval gate) wins over learned volume
        s["posts_per_platform"] = max(3, min(8, posts))
    s["replies_per_platform"] = max(3, min(10, replies))
    if weights:
        s["format_weights"] = {**(s.get("format_weights") or {}), **weights}
    s.update(hard)
    s["planner"] = PLANNER_VERSION
    base.settings = s
    base.decisions.append(Decision(
        "L1.neighbours", {"posts_per_platform": s["posts_per_platform"], "replies_per_platform": s["replies_per_platform"], "format_weights": s.get("format_weights")},
        f"{len(winners)} best-growing of {len(usable)} similar company-weeks (median growth {statistics.median([n.growth_wow for n in winners]):+.0%}) "
        f"ran {posts} posts and {replies} replies per platform; adopting their settings" + (" (volume held by the approval gate)" if gated else "") + "."))
    return base, winners
