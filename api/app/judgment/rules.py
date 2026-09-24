"""Scorecard rules, v0. Five channels, each scored 0-10 by a named function that
returns (score, rationale, evidence). The fix for each channel is chosen from FIXES by
the lowest-scoring sub-rule. Versioned: bump RULES_VERSION when any threshold changes,
so plan rows record which rules produced them.

These thresholds are opinions, written down so they can be argued with and then
learned from (Component 12 replaces them with outcomes)."""
from dataclasses import dataclass, field

from .signals import Signals

RULES_VERSION = "v0.1"


@dataclass
class ChannelScore:
    channel: str
    score: int                       # 0..10
    rationale: list[str] = field(default_factory=list)
    evidence: dict = field(default_factory=dict)
    fix_id: str = ""
    fix: str = ""
    weakest: str = ""


def _clamp(x: float) -> int:
    return max(0, min(10, int(round(x))))


# ---------- founder distribution ----------
def founder_distribution(s: Signals) -> ChannelScore:
    c = ChannelScore("founder_distribution", 0)
    if not s.founders:
        c.rationale.append("No founder accounts connected.")
        c.weakest = "no_accounts"
        return c
    best = max(s.founders, key=lambda f: f.linkedin_impressions_30d + f.x_impressions_30d)
    imp = best.linkedin_impressions_30d + best.x_impressions_30d
    posts = best.linkedin_posts_30d + best.x_posts_30d
    followers = best.linkedin_followers + best.x_followers
    c.evidence = {"founder": best.name, "impressions_30d": imp, "posts_30d": posts, "followers": followers,
                  "channels": [ch for ch, ok in (("linkedin", best.has_linkedin), ("x", best.has_x)) if ok]}
    sub = {}
    sub["cadence"] = 10 if posts >= 20 else 7 if posts >= 12 else 4 if posts >= 4 else 1
    sub["reach"] = 10 if imp >= 500_000 else 8 if imp >= 100_000 else 6 if imp >= 25_000 else 3 if imp >= 5_000 else 1
    sub["channels"] = 10 if best.has_linkedin and best.has_x else 5
    c.score = _clamp(0.4 * sub["cadence"] + 0.4 * sub["reach"] + 0.2 * sub["channels"])
    c.weakest = min(sub, key=sub.get)
    c.rationale = [
        f"{best.name} posted {posts} times in 30 days (cadence {sub['cadence']}/10).",
        f"{imp:,} impressions in 30 days (reach {sub['reach']}/10).",
        f"Active on {', '.join(c.evidence['channels']) or 'no channels'} (coverage {sub['channels']}/10).",
    ]
    return c


# ---------- ICP attention ----------
def icp_attention(s: Signals) -> ChannelScore:
    c = ChannelScore("icp_attention", 0)
    if not s.icp:
        c.rationale.append("No ICP defined; run intake.")
        c.weakest = "no_icp"
        return c
    personas = s.icp.get("personas") or []
    firmo = s.icp.get("firmographics") or {}
    sub = {}
    sub["definition"] = 10 if (s.icp.get("description") and len(personas) >= 2 and firmo) else 5 if s.icp.get("description") else 1
    # v0 has no attention map yet, so 'targeting' is proxied by whether personas name where they pay attention
    sub["targeting"] = 8 if any(p.get("where_they_pay_attention") for p in personas if isinstance(p, dict)) else 2
    sub["proof"] = 8 if len(s.proof_points) >= 3 else 5 if s.proof_points else 2
    c.score = _clamp(0.4 * sub["definition"] + 0.4 * sub["targeting"] + 0.2 * sub["proof"])
    c.weakest = min(sub, key=sub.get)
    c.evidence = {"personas": len(personas), "proof_points": len(s.proof_points), "icp_version": s.icp.get("version")}
    c.rationale = [
        f"ICP definition {sub['definition']}/10: {len(personas)} personas, firmographics {'set' if firmo else 'missing'}.",
        f"Targeting {sub['targeting']}/10: {'personas say where they pay attention' if sub['targeting'] > 5 else 'no attention map yet'}.",
        f"Proof {sub['proof']}/10: {len(s.proof_points)} proof points found on the site.",
    ]
    return c


# ---------- search ----------
def search(s: Signals) -> ChannelScore:
    c = ChannelScore("search", 0)
    sub = {}
    sub["indexed"] = 10 if s.pages_indexed >= 200 else 7 if s.pages_indexed >= 50 else 4 if s.pages_indexed >= 10 else 1
    sub["impressions"] = 10 if s.search_impressions_30d >= 50_000 else 7 if s.search_impressions_30d >= 10_000 else 4 if s.search_impressions_30d >= 1_000 else 1
    sub["data_assets"] = 9 if len(s.data_assets) >= 2 else 5 if s.data_assets else 2
    sub["measurement"] = 10 if s.has_search_console else 3
    c.score = _clamp(0.35 * sub["indexed"] + 0.3 * sub["impressions"] + 0.2 * sub["data_assets"] + 0.15 * sub["measurement"])
    c.weakest = min(sub, key=sub.get)
    c.evidence = {"pages_indexed": s.pages_indexed, "search_impressions_30d": s.search_impressions_30d,
                  "data_assets": s.data_assets, "search_console": s.has_search_console}
    c.rationale = [
        f"{s.pages_indexed} pages indexed ({sub['indexed']}/10); {s.search_impressions_30d:,} search impressions in 30 days ({sub['impressions']}/10).",
        f"{len(s.data_assets)} data assets that could power programmatic pages ({sub['data_assets']}/10).",
        f"Search Console {'connected' if s.has_search_console else 'not connected'} ({sub['measurement']}/10).",
    ]
    return c


# ---------- launches ----------
def launches(s: Signals) -> ChannelScore:
    c = ChannelScore("launches", 0)
    sub = {"frequency": 9 if s.launches_12m >= 4 else 6 if s.launches_12m >= 2 else 3 if s.launches_12m == 1 else 1,
           "proof_to_launch": 8 if len(s.proof_points) >= 2 else 3}
    c.score = _clamp(0.6 * sub["frequency"] + 0.4 * sub["proof_to_launch"])
    c.weakest = min(sub, key=sub.get)
    c.evidence = {"launches_12m": s.launches_12m, "launchable_proof": s.proof_points[:5]}
    c.rationale = [
        f"{s.launches_12m} launches in the last 12 months ({sub['frequency']}/10).",
        f"{len(s.proof_points)} proof points that could anchor a launch ({sub['proof_to_launch']}/10).",
    ]
    return c


# ---------- onboarding ----------
def onboarding(s: Signals) -> ChannelScore:
    c = ChannelScore("onboarding", 0)
    sub = {}
    sub["self_serve"] = 9 if s.has_self_serve_signup else 3 if s.has_self_serve_signup is None else 2
    sub["attribution"] = 10 if s.has_signup_source_field else 1
    sub["signups"] = 8 if s.signups_30d >= 100 else 5 if s.signups_30d >= 20 else 2
    if s.site_audit_score is not None:
        sub["audit"] = int(round(s.site_audit_score))
        c.score = _clamp(0.3 * sub["self_serve"] + 0.3 * sub["attribution"] + 0.15 * sub["signups"] + 0.25 * sub["audit"])
    else:
        c.score = _clamp(0.4 * sub["self_serve"] + 0.35 * sub["attribution"] + 0.25 * sub["signups"])
    c.weakest = min(sub, key=sub.get)
    c.evidence = {"self_serve": s.has_self_serve_signup, "signup_source_field": s.has_signup_source_field,
                  "signups_30d": s.signups_30d}
    c.rationale = [
        f"Self-serve signup: {'yes' if s.has_self_serve_signup else 'unknown' if s.has_self_serve_signup is None else 'no'} ({sub['self_serve']}/10).",
        f"'How did you hear about us' field: {'present' if s.has_signup_source_field else 'missing'} ({sub['attribution']}/10).",
        f"{s.signups_30d} signups in 30 days ({sub['signups']}/10).",
    ]
    return c


CHANNELS = [founder_distribution, icp_attention, search, launches, onboarding]

# ---------- fix library: one concrete fix per weakest sub-rule ----------
FIXES = {
    ("founder_distribution", "no_accounts"): ("connect_accounts", "Connect the founder's LinkedIn and X so the product can post and measure."),
    ("founder_distribution", "cadence"): ("cadence_12", "Move to 12+ posts a month from one weekly 45-minute interview; the voice engine drafts, the founder taps."),
    ("founder_distribution", "reach"): ("reply_first", "Reply daily to 10 threads the ICP actually reads (attention map) before posting; reach follows replies."),
    ("founder_distribution", "channels"): ("add_channel", "Add the missing channel and cross-post the same material in that platform's format."),
    ("icp_attention", "no_icp"): ("run_intake", "Run intake with three real customers so the ICP is defined."),
    ("icp_attention", "definition"): ("sharpen_icp", "Sharpen the ICP to one narrow segment with two personas and firmographics; everything downstream targets it."),
    ("icp_attention", "targeting"): ("attention_map", "Build the attention map: 300 accounts the ICP follows and the threads they reply to."),
    ("icp_attention", "proof"): ("surface_proof", "Put named customers, numbers and logos in the founder's posts and on the site; proof is what the ICP shares."),
    ("search", "indexed"): ("page_factory", "Generate a first cluster of 30-50 pages from product data ([product] for [segment], [competitor] alternative)."),
    ("search", "impressions"): ("page_factory", "Ship data-backed pages for the ICP's own search terms; impressions follow indexing within 30 days."),
    ("search", "data_assets"): ("find_data", "Identify one data asset the product produces that no competitor publishes; that becomes the page and tool source."),
    ("search", "measurement"): ("connect_search_console", "Connect Google Search Console so pages and impressions are measured, not guessed."),
    ("launches", "frequency"): ("launch_calendar", "Schedule one launch (feature drop or Product Hunt) in the next 6 weeks with the launch kit."),
    ("launches", "proof_to_launch"): ("customer_launch", "Turn the strongest customer result into a joint launch with that customer."),
    ("onboarding", "self_serve"): ("self_serve_path", "Add a self-serve path (trial, sandbox or demo) so inbound attention converts without a sales call."),
    ("onboarding", "attribution"): ("signup_source_field", "Add the one-line 'how did you hear about us' field; it is the only reliable attribution at this stage."),
    ("onboarding", "signups"): ("activation_audit", "Run the 40-point onboarding audit and fix the top three drop-offs."),
    ("onboarding", "audit"): ("site_rewrite", "Approve the generated site changes for the failed audit checks and ship the variant."),
}


def score_all(s: Signals) -> list[ChannelScore]:
    out = []
    for fn in CHANNELS:
        c = fn(s)
        fid, ftext = FIXES.get((c.channel, c.weakest), ("review", "Review manually."))
        c.fix_id, c.fix = fid, ftext
        out.append(c)
    return out
