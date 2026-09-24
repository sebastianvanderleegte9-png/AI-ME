"""The 12 post formats. Each is a shape a claim can be poured into. The format
picker matches claim type to format; the drafter fills the shape in the founder's
voice. Per-format approval rates are tracked so the sequencer learns which shapes
work for which founder.

`needs` says what kind of material the format requires from the interview.
`visual` says which card template fits (Component 3 visual engine), or None."""

FORMATS = {
    "contrarian_take": {
        "needs": ["opinion"],
        "shape": "State the common belief in one line. Say why it's wrong from direct experience. End on what to do instead.",
        "linkedin_len": (600, 1100), "x_len": (120, 270), "visual": None,
    },
    "customer_story": {
        "needs": ["story", "customer"],
        "shape": "Who the customer is (specific), what they were doing before, what changed, one number. No adjectives.",
        "linkedin_len": (700, 1300), "x_len": (150, 280), "visual": "before_after",
    },
    "build_log": {
        "needs": ["story", "product"],
        "shape": "What we shipped this week, why, what broke, what we learned. Present tense, first person.",
        "linkedin_len": (500, 1000), "x_len": (120, 270), "visual": "screenshot_annotated",
    },
    "teardown": {
        "needs": ["observation"],
        "shape": "Pick one real thing (a page, a flow, a post). Say what's wrong specifically. Say the fix. Name it.",
        "linkedin_len": (600, 1200), "x_len": (150, 280), "visual": "screenshot_annotated",
    },
    "number_with_lesson": {
        "needs": ["number"],
        "shape": "Lead with the number. Two lines of context. One lesson. Stop.",
        "linkedin_len": (300, 700), "x_len": (80, 220), "visual": "number_card",
    },
    "before_after": {
        "needs": ["story", "number"],
        "shape": "Before: two lines. After: two lines. What made the difference: one line.",
        "linkedin_len": (400, 800), "x_len": (120, 260), "visual": "before_after",
    },
    "framework": {
        "needs": ["process"],
        "shape": "Name the thing. 3-5 steps, each one line, each concrete. When it does not apply.",
        "linkedin_len": (600, 1200), "x_len": (180, 280), "visual": "steps",
    },
    "question": {
        "needs": ["opinion"],
        "shape": "One sharp question the ICP argues about. Your position in two lines. Ask.",
        "linkedin_len": (200, 500), "x_len": (60, 200), "visual": None,
    },
    "prediction": {
        "needs": ["opinion"],
        "shape": "What will be true in 12-24 months. Why (evidence you have seen). What to do now.",
        "linkedin_len": (500, 1000), "x_len": (120, 270), "visual": None,
    },
    "mistake": {
        "needs": ["story"],
        "shape": "What we got wrong. What it cost (number if possible). What we changed. No moral.",
        "linkedin_len": (500, 1000), "x_len": (120, 270), "visual": None,
    },
    "list": {
        "needs": ["observation", "process"],
        "shape": "3-7 items, each a complete specific thought. No 'and more'. Title says what the list is for.",
        "linkedin_len": (500, 1100), "x_len": (150, 280), "visual": "steps",
    },
    "quote_with_take": {
        "needs": ["quote"],
        "shape": "Quote (attributed, from the interview or a customer). Why it matters to the ICP. One line.",
        "linkedin_len": (300, 700), "x_len": (100, 250), "visual": "quote_card",
    },
}

CLAIM_TYPES = ["opinion", "story", "customer", "product", "observation", "number", "process", "quote"]


def formats_for(claim_types: set[str], allowed: list[str] | None = None) -> list[str]:
    out = [k for k, f in FORMATS.items() if set(f["needs"]) <= claim_types]
    if allowed:
        out = [k for k in out if k in allowed]
    return out
