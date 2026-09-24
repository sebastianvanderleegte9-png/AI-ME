"""The signup-source field: one free-text question on the founder's signup form,
'how did you hear about us?', posted to us. Classified by rules first (cheap, explainable),
LLM only for the leftovers. This is the only reliable attribution at seed stage."""
import re

from ..interfaces import get_llm

RULES: list[tuple[str, str]] = [
    ("linkedin", r"\blinked ?in\b|\bli\b"),
    ("x", r"\btwitter\b|\bx\.com\b|\bon x\b|\btweet"),
    ("search", r"\bgoogl\w*|\bsearch\w*|\bbing\b|\bchatgpt\b|\bperplexity\b|\bseo\b"),
    ("launch", r"\bproduct ?hunt\b|\blaunch\b|\bhacker ?news\b|\bhn\b"),
    ("referral", r"\bfriend\b|\bcolleague\b|\breferr|\brecommend|\bword of mouth\b|\bfrom [a-z]+ at\b"),
    ("newsletter", r"\bnewsletter\b|\bsubstack\b|\bemail\b"),
    ("podcast", r"\bpodcast\b|\byoutube\b|\bvideo\b"),
    ("event", r"\bconference\b|\bevent\b|\bmeetup\b|\bwebinar\b"),
]

CLASSIFY_SYS = """Classify a signup's answer to 'how did you hear about us?' into exactly one of:
linkedin, x, search, launch, referral, newsletter, podcast, event, other. Reply with the label only."""

LABELS = {r[0] for r in RULES} | {"other"}


def classify(answer: str) -> tuple[str, str]:
    low = answer.lower().strip()
    if not low:
        return "other", "rules:v1"
    for label, rx in RULES:
        if re.search(rx, low):
            return label, "rules:v1"
    out = get_llm().complete(CLASSIFY_SYS, answer[:300], purpose="signup_classify", temperature=0, max_tokens=5).text
    label = out.strip().lower().split()[0].strip(".,") if out and not out.startswith("[fake:") else "other"
    return (label if label in LABELS else "other"), "llm:v1"
