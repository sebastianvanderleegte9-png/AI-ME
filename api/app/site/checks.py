"""The 40-point onboarding and site audit (Component 10). Each check is a named function
over a Snapshot of the site (fetched HTML + a scripted walkthrough of the signup flow).
Returns pass/fail + evidence. Categories mirror what the tweet calls 'fundamentally
understands great onboarding and attention spans': can the ICP tell what this is in
5 seconds, can they start in 60, and do they reach value in the first session.

Weights sum to 100 per category is NOT required; the score is weighted pass rate."""
from dataclasses import dataclass, field
import re

AUDIT_VERSION = "audit-v1"


@dataclass
class Snapshot:
    url: str
    html: str = ""
    title: str = ""
    text: str = ""                       # visible text
    headings: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    forms: list[dict] = field(default_factory=list)   # [{action, fields:[{name,type,required}], has_source_field}]
    images: int = 0
    scripts: int = 0
    word_count: int = 0
    load_ms: int | None = None
    # walkthrough (headless): what happened when we tried to sign up
    signup_url: str | None = None
    signup_steps: int | None = None
    signup_fields: int | None = None
    requires_card: bool | None = None
    requires_call: bool | None = None
    first_screen_after_signup: str | None = None   # text of the first thing a new user sees
    activation_email_subject: str | None = None
    has_demo_or_video: bool = False
    mobile_ok: bool | None = None
    proof_points: list[str] = field(default_factory=list)
    icp_terms: list[str] = field(default_factory=list)


@dataclass
class Check:
    id: str
    category: str
    weight: int
    title: str
    fix: str


@dataclass
class Result:
    check: Check
    passed: bool
    evidence: str


def _has(t: str, *words) -> bool:
    low = t.lower()
    return any(w in low for w in words)


# ---- clarity (can the ICP tell what this is in 5 seconds) ----
def c01(s): return (bool(s.headings) and len(s.headings[0].split()) <= 12, f"h1: {s.headings[0] if s.headings else 'none'}")
def c02(s): return (bool(s.headings) and not _has(s.headings[0], "reinvent", "revolution", "future of", "next generation", "unleash", "empower", "seamless"), "h1 free of category words")
def c03(s): return (any(w in s.text.lower() for w in s.icp_terms) if s.icp_terms else False, f"ICP terms on page: {[w for w in s.icp_terms if w in s.text.lower()][:3]}")
def c04(s): return (_has(s.text[:1500], "for ", "helps ", "so you", "so that"), "who-it-is-for stated above the fold")
def c05(s): return (s.title != "" and len(s.title) <= 60, f"title: {s.title[:60]} ({len(s.title)} chars)")
def c06(s): return (bool(s.proof_points), f"proof points visible: {len(s.proof_points)}")
def c07(s): return (bool(re.search(r"\b\d[\d,]*(%|x|\+| hours| minutes| days| agents| users| customers| teams)", s.text)), "at least one number on the page")
def c08(s): return (s.has_demo_or_video, "demo, screenshot or video present")
def c09(s): return (s.word_count <= 900, f"{s.word_count} words on the landing page (<= 900)")
def c10(s): return (s.images <= 25 and s.scripts <= 25, f"{s.images} images, {s.scripts} scripts")

# ---- action (can they start in 60 seconds) ----
def c11(s): return (any(_has(l, "sign", "start", "try", "demo", "get started") for l in s.links[:40]), "a start/try/demo link in the top of the page")
def c12(s): return (s.signup_url is not None, f"signup reachable: {s.signup_url}")
def c13(s): return (s.signup_steps is not None and s.signup_steps <= 2, f"signup steps: {s.signup_steps}")
def c14(s): return (s.signup_fields is not None and s.signup_fields <= 4, f"signup fields: {s.signup_fields}")
def c15(s): return (s.requires_card is False, f"card required: {s.requires_card}")
def c16(s): return (s.requires_call is False, f"sales call required before use: {s.requires_call}")
def c17(s): return (any(f.get("has_source_field") for f in s.forms), "'how did you hear about us' field on signup")
def c18(s): return (not _has(s.text, "book a demo") or s.signup_url is not None, "self-serve path exists beside 'book a demo'")
def c19(s): return (s.load_ms is None or s.load_ms <= 3000, f"load {s.load_ms} ms")
def c20(s): return (s.mobile_ok is not False, f"mobile layout ok: {s.mobile_ok}")

# ---- first session (do they reach value) ----
def c21(s): return (s.first_screen_after_signup is not None, "we could see the first screen after signup")
def c22(s): return (bool(s.first_screen_after_signup) and not _has(s.first_screen_after_signup, "welcome", "getting started", "tour") , "first screen is the product, not a tour")
def c23(s): return (bool(s.first_screen_after_signup) and _has(s.first_screen_after_signup, "create", "connect", "import", "upload", "add", "paste", "try"), "first screen asks for one action")
def c24(s): return (bool(s.first_screen_after_signup) and len(s.first_screen_after_signup.split()) <= 120, "first screen under 120 words")
def c25(s): return (not (s.first_screen_after_signup and _has(s.first_screen_after_signup, "watch", "video", "minute")), "no mandatory video before the product")
def c26(s): return (s.activation_email_subject is not None, f"activation email exists: {s.activation_email_subject}")
def c27(s): return (bool(s.activation_email_subject) and not _has(s.activation_email_subject, "welcome to"), "activation email subject is an action, not 'welcome'")
def c28(s): return (bool(s.first_screen_after_signup) and _has(s.first_screen_after_signup, "example", "sample", "template", "demo data"), "sample data or example available at first run")
def c29(s): return (bool(s.first_screen_after_signup) and not _has(s.first_screen_after_signup, "invite your team", "upgrade", "pricing"), "no upsell before first value")
def c30(s): return (_has(s.text, "minute", "seconds", "in a day", "same day", "today") , "time-to-value stated somewhere")

# ---- trust and follow-through ----
def c31(s): return (_has(s.text, "privacy", "security", "soc", "gdpr"), "privacy/security mentioned")
def c32(s): return (bool(re.search(r"\b(inc|llc|ltd|gmbh|a\.s\.|©|\(c\))\b", s.text.lower())), "company legal identity on page")
def c33(s): return (_has(s.text, "founder", "team", "about"), "a human behind the product")
def c34(s): return (len([l for l in s.links if l.startswith("http") and "linkedin.com" in l or "x.com" in l or "twitter.com" in l]) > 0, "founder social linked")
def c35(s): return (_has(s.text, "pricing", "free", "$"), "pricing or 'free' visible")
def c36(s): return (not _has(s.text, "lorem ipsum", "coming soon", "under construction"), "no placeholder text")
def c37(s): return (len(s.headings) >= 3, f"{len(s.headings)} headings (structure)")
def c38(s): return (_has(s.text, "customer", "used by", "trusted by", "case"), "customer language present")
def c39(s): return (s.title.lower() not in ("home", "index", "untitled"), "meaningful page title")
def c40(s): return (bool(s.forms), "at least one form on the site")


CHECKS: list[tuple[Check, callable]] = [
    (Check("c01", "clarity", 4, "One-line headline under 12 words", "Rewrite the h1 to say what it does for whom in one line."), c01),
    (Check("c02", "clarity", 3, "Headline has no category words", "Replace 'reinvent/revolutionize/next-gen' with the specific job it does."), c02),
    (Check("c03", "clarity", 4, "ICP's own terms on the page", "Use the words the ICP uses for their job and problem, above the fold."), c03),
    (Check("c04", "clarity", 3, "Who it is for, above the fold", "Add 'for [segment]' to the hero."), c04),
    (Check("c05", "clarity", 1, "Title tag under 60 chars", "Set a title tag: product — job for segment."), c05),
    (Check("c06", "clarity", 4, "Proof points visible", "Put named customers, numbers or logos on the landing page."), c06),
    (Check("c07", "clarity", 3, "A number on the page", "State one measured result."), c07),
    (Check("c08", "clarity", 3, "Demo or screenshot", "Show the product; a 60-second screen recording beats copy."), c08),
    (Check("c09", "clarity", 2, "Landing page under 900 words", "Cut to the hero, proof, how it works, CTA."), c09),
    (Check("c10", "clarity", 1, "Page weight sane", "Remove unused scripts and oversized images."), c10),
    (Check("c11", "action", 3, "Start link at the top", "Add a primary CTA in the nav and hero."), c11),
    (Check("c12", "action", 4, "Signup reachable", "Make signup a link from the landing page."), c12),
    (Check("c13", "action", 4, "Signup in two steps or fewer", "Collapse signup to email + one step."), c13),
    (Check("c14", "action", 3, "Four fields or fewer", "Remove every field you do not use on day one."), c14),
    (Check("c15", "action", 3, "No card up front", "Take the card at upgrade, not signup."), c15),
    (Check("c16", "action", 4, "No sales call required", "Add a self-serve or sandbox path beside the demo."), c16),
    (Check("c17", "action", 4, "'How did you hear about us' field", "Install the signup-source widget (one script tag)."), c17),
    (Check("c18", "action", 2, "Self-serve beside 'book a demo'", "Offer both; route small teams to self-serve."), c18),
    (Check("c19", "action", 2, "Loads in under 3s", "Fix the largest image and blocking scripts."), c19),
    (Check("c20", "action", 2, "Works on mobile", "Half of founder-post clicks are mobile; fix the layout."), c20),
    (Check("c21", "first_session", 2, "First screen observable", "Let us (and you) see what a new user sees."), c21),
    (Check("c22", "first_session", 4, "First screen is the product", "Drop the tour; land in the product."), c22),
    (Check("c23", "first_session", 4, "One action on first screen", "Ask for exactly one thing: connect, upload, paste."), c23),
    (Check("c24", "first_session", 2, "First screen under 120 words", "Cut the copy; keep the action."), c24),
    (Check("c25", "first_session", 3, "No mandatory video", "Replace the video with a two-minute in-product walkthrough."), c25),
    (Check("c26", "first_session", 3, "Activation email exists", "Send one email after signup with the single next action."), c26),
    (Check("c27", "first_session", 2, "Activation email is an action", "Subject: the action, not 'Welcome to X'."), c27),
    (Check("c28", "first_session", 3, "Sample data available", "Offer example data so value is visible before their data is in."), c28),
    (Check("c29", "first_session", 2, "No upsell before value", "Move invites and upgrades after the first result."), c29),
    (Check("c30", "first_session", 2, "Time-to-value stated", "Say how long to the first result."), c30),
    (Check("c31", "trust", 2, "Privacy/security mentioned", "Add one line and a link."), c31),
    (Check("c32", "trust", 1, "Legal identity", "Footer: company name and entity."), c32),
    (Check("c33", "trust", 2, "A human behind it", "Founder name and a line."), c33),
    (Check("c34", "trust", 2, "Founder social linked", "Link the founder's LinkedIn/X (their posts are your proof)."), c34),
    (Check("c35", "trust", 2, "Pricing or free visible", "Say the price or say free."), c35),
    (Check("c36", "trust", 2, "No placeholder text", "Remove 'coming soon' and lorem ipsum."), c36),
    (Check("c37", "trust", 1, "Page has structure", "Three or more headings."), c37),
    (Check("c38", "trust", 2, "Customer language", "'Used by', 'customers', a case."), c38),
    (Check("c39", "trust", 1, "Meaningful title", "Not 'Home'."), c39),
    (Check("c40", "trust", 1, "A form exists", "Somewhere to sign up or ask."), c40),
]
assert len(CHECKS) == 40


def run(snapshot: Snapshot) -> list[Result]:
    out = []
    for check, fn in CHECKS:
        try:
            ok, ev = fn(snapshot)
        except Exception as e:  # noqa: BLE001
            ok, ev = False, f"error: {e}"
        out.append(Result(check, bool(ok), str(ev)))
    return out


def score(results: list[Result]) -> dict:
    by_cat: dict[str, dict] = {}
    for r in results:
        d = by_cat.setdefault(r.check.category, {"got": 0, "max": 0, "failed": []})
        d["max"] += r.check.weight
        if r.passed:
            d["got"] += r.check.weight
        else:
            d["failed"].append(r.check.id)
    total_got = sum(d["got"] for d in by_cat.values())
    total_max = sum(d["max"] for d in by_cat.values())
    return {"overall": round(10 * total_got / total_max, 1) if total_max else 0,
            "categories": {k: {"score": round(10 * v["got"] / v["max"], 1), "failed": v["failed"]} for k, v in by_cat.items()},
            "version": AUDIT_VERSION}
