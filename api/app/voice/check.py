"""Voice-match check: every draft passes this before a founder ever sees it.
Three parts, combined into one 0..1 score plus hard fails:
  1. banned phrases (hard fail) — the founder's list plus the default slop list
  2. slop patterns (penalties) — the tells of generated text
  3. similarity to the founder's own samples (embedding cosine, when samples exist)
Below THRESHOLD the draft is regenerated, never shown."""
from dataclasses import dataclass, field
import re

from ..interfaces import get_llm

THRESHOLD = 0.62

# Structural tells of generated text, independent of vocabulary.
SLOP_PATTERNS: list[tuple[str, str, float]] = [
    ("triadic_adjectives", r"\b\w+, \w+, and \w+\b", 0.05),
    ("its_not_x_its_y", r"\bit'?s not (just |about )?\w+[^.]{0,40}, it'?s\b", 0.15),
    ("rhetorical_setup", r"\b(here'?s the (thing|truth|kicker)|let that sink in|read that again)\b", 0.2),
    ("emoji_bullets", r"^[✅🔥🚀💡👉➡️•]\s", 0.1),
    ("hashtag_pile", r"(#\w+\s*){3,}", 0.15),
    ("excess_exclaim", r"!{2,}|(!.*){3,}", 0.1),
    ("colon_hook", r"^[A-Z][^.!?]{0,60}:\s*$", 0.05),
    ("em_dash_pile", r"(—.*){3,}", 0.08),
    ("generic_cta", r"(what do you think\?|\bthoughts\?|\bagree\?|drop a comment|follow for more)", 0.12),
]


@dataclass
class CheckResult:
    score: float
    passed: bool
    banned_hits: list[str] = field(default_factory=list)
    pattern_hits: list[str] = field(default_factory=list)
    similarity: float | None = None
    notes: list[str] = field(default_factory=list)


def _cos(a, b):
    return sum(x * y for x, y in zip(a, b))


def check(text: str, *, banned: list[str], samples: list[str], casing: str | None = None) -> CheckResult:
    low = text.lower()
    banned_hits = [b for b in banned if b.lower() in low]
    pattern_hits = [name for name, rx, _ in SLOP_PATTERNS if re.search(rx, text, re.I | re.M)]
    penalty = sum(w for name, _, w in SLOP_PATTERNS if name in pattern_hits)

    sim = None
    if samples:
        llm = get_llm()
        vecs = llm.embed([text] + samples[:20], purpose="voice_check")
        sims = [_cos(vecs[0], v) for v in vecs[1:]]
        sim = max(sims) if sims else None

    notes = []
    if casing == "lower" and text != text.lower() and sum(ch.isupper() for ch in text) > 3:
        penalty += 0.1
        notes.append("founder writes lowercase; draft has capitals")

    # base 0.75 (clean text passes); similarity to the founder's own writing moves it
    # +/- 0.15. Real embeddings give ~0.3-0.9 for same-author text; hashed fakes give ~0,
    # so the fake path is neutral rather than punishing.
    base = 0.75
    if sim is not None:
        base += max(-0.15, min(0.15, (sim - 0.3) * 0.5))
    score = max(0.0, min(1.0, base - penalty))
    passed = not banned_hits and score >= THRESHOLD
    return CheckResult(score=round(score, 3), passed=passed, banned_hits=banned_hits,
                       pattern_hits=pattern_hits, similarity=None if sim is None else round(sim, 3), notes=notes)
