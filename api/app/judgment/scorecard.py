"""Scorecard = signals -> five channel scores -> 90-day sequence -> plan row.
The LLM writes only the narrative; the numbers and the order come from rules."""
from datetime import date, timedelta
import json

from sqlalchemy.orm import Session

from ..interfaces import get_llm
from ..models import Company, Plan
from .rules import RULES_VERSION, ChannelScore, score_all
from .signals import Signals, gather

NARRATIVE_SYS = """You are a marketing engineer writing the narrative for a growth diagnostic.
You are given five channel scores with rationale and one fix each, plus the product and ICP.
Write for the founder, plainly, no hype, no buzzwords. Return JSON:
  headline (one sentence: the single most important finding),
  summary (3-4 sentences: where the company is and what the 90 days should do),
  per_channel ({channel: one or two sentences interpreting the score for THIS company}),
  first_two_weeks (list of 3-5 concrete actions)."""

# Sequencing rules v0: what to build first.
# Order by (a) prerequisite, (b) speed to a visible number, (c) score gap.
PREREQ = {"icp_attention": [], "founder_distribution": ["icp_attention"], "onboarding": [],
          "search": ["icp_attention"], "launches": ["founder_distribution"]}
SPEED_TO_SIGNAL = {"founder_distribution": 1, "icp_attention": 1, "onboarding": 2, "launches": 3, "search": 4}


def sequence(scores: list[ChannelScore]) -> list[dict]:
    by = {c.channel: c for c in scores}
    # always-first: attribution, because nothing else can be measured without it
    order: list[str] = []
    if by["onboarding"].weakest == "attribution":
        order.append("onboarding")
    remaining = [c for c in scores if c.channel not in order]
    remaining.sort(key=lambda c: (SPEED_TO_SIGNAL[c.channel], c.score))
    for c in remaining:
        for p in PREREQ[c.channel]:
            if p not in order and p in by:
                order.append(p)
        if c.channel not in order:
            order.append(c.channel)
    # assign phases: weeks 1-2 install, 3-6 first results, 7-12 compound
    phases = [(1, 2), (3, 6), (7, 12)]
    out = []
    for i, ch in enumerate(order):
        wk = phases[min(i // 2, 2)]
        out.append({"channel": ch, "start_week": wk[0], "end_week": wk[1], "fix_id": by[ch].fix_id,
                    "fix": by[ch].fix, "score_now": by[ch].score,
                    "target_score_12w": min(10, by[ch].score + (4 if by[ch].score < 5 else 2))})
    return out


def targets_for(scores: list[ChannelScore], sig: Signals) -> dict:
    base_imp = sum(f.linkedin_impressions_30d + f.x_impressions_30d for f in sig.founders)
    return {
        "impressions_icp_weekly": max(1000, int(base_imp / 4 * 0.2)),   # baseline: assume 20% of impressions are ICP
        "impressions_icp_weekly_12w": max(3000, int(base_imp / 4 * 0.2 * 3)),  # 3x
        "followers_icp_12w": 300,
        "pages_indexed_12w": 30 if any(c.channel == "search" and c.score < 6 for c in scores) else 0,
        "approval_rate_min": 0.7,
    }


def build_scorecard(db: Session, company: Company, week_start: date | None = None) -> Plan:
    sig = gather(db, company)
    scores = score_all(sig)
    seq = sequence(scores)
    tg = targets_for(scores, sig)

    narrative = {}
    try:
        text = get_llm().complete(
            NARRATIVE_SYS,
            json.dumps({"company": sig.company_name, "stage": sig.stage, "product": sig.product_summary,
                        "icp": sig.icp, "scores": [c.__dict__ for c in scores], "sequence": seq}, default=str),
            purpose="scorecard_narrative", json_mode=True, max_tokens=1200).text
        narrative = json.loads(text)
        if narrative.get("fake"):
            narrative = _fallback_narrative(scores, seq)
    except Exception:  # noqa: BLE001
        narrative = _fallback_narrative(scores, seq)

    scorecard = {c.channel: {"score": c.score, "rationale": c.rationale, "evidence": c.evidence,
                             "weakest": c.weakest, "fix_id": c.fix_id, "fix": c.fix,
                             "interpretation": narrative.get("per_channel", {}).get(c.channel, "")}
                 for c in scores}
    scorecard["_narrative"] = {k: narrative.get(k) for k in ("headline", "summary", "first_two_weeks")}
    scorecard["_overall"] = round(sum(c.score for c in scores) / len(scores), 1)

    ws = week_start or (date.today() - timedelta(days=date.today().weekday()))
    plan = db.query(Plan).filter_by(company_id=company.id, week_start=ws).first()
    if plan is None:
        plan = Plan(company_id=company.id, week_start=ws, generated_by="rules")
        db.add(plan)
    plan.scorecard, plan.sequence, plan.targets = scorecard, seq, tg
    plan.generated_by = "rules"
    plan.rules_version = RULES_VERSION
    db.commit()
    db.refresh(plan)
    return plan


def _fallback_narrative(scores: list[ChannelScore], seq: list[dict]) -> dict:
    """Used when no real LLM is configured. Rule-generated, so the diagnostic still reads."""
    from .render import LABEL
    L = lambda ch: LABEL.get(ch, ch.replace("_", " "))  # noqa: E731
    worst = min(scores, key=lambda c: c.score)
    best = max(scores, key=lambda c: c.score)
    first = seq[0]
    return {
        "headline": f"{L(worst.channel)} is the biggest gap ({worst.score}/10); "
                    f"{L(first['channel']).lower()} is what to build first.",
        "summary": f"The strongest channel today is {L(best.channel).lower()} at {best.score}/10 and the weakest is "
                   f"{L(worst.channel).lower()} at {worst.score}/10. Over 90 days the sequence installs "
                   f"{L(seq[0]['channel']).lower()} and {L(seq[1]['channel']).lower()} first, then compounds "
                   f"into {', '.join(L(s['channel']).lower() for s in seq[2:])}. The single number to watch is "
                   f"impressions inside the ICP, reported every Friday.",
        "per_channel": {},  # rationale bullets already say it; no LLM to add interpretation
        "first_two_weeks": [s["fix"] for s in seq[:3]],
    }
