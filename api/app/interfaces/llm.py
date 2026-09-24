from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import hashlib
import json


@dataclass
class Completion:
    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    meta: dict = field(default_factory=dict)


class LLM(ABC):
    """Text generation and embeddings behind one interface.

    Prompt text and model name are pinned per component (Principle: model governance);
    a component passes `purpose` so cost and quality can be tracked per use."""

    @abstractmethod
    def complete(self, system: str, user: str, *, purpose: str, model: str | None = None,
                 temperature: float = 0.4, max_tokens: int = 1024, json_mode: bool = False) -> Completion: ...

    @abstractmethod
    def embed(self, texts: list[str], *, purpose: str) -> list[list[float]]: ...


class FakeLLM(LLM):
    """Deterministic stand-in. Returns a recognisable string (or valid JSON when asked)
    and a stable pseudo-embedding derived from a hash of the text, so similarity
    between identical texts is 1.0 and between different texts is low."""

    DIM = 1536
    FAKE_EMBEDDINGS = True

    def complete(self, system, user, *, purpose, model=None, temperature=0.4, max_tokens=1024, json_mode=False):
        if json_mode:
            text = json.dumps({"fake": True, "purpose": purpose, "echo": user[:80]})
        else:
            text = f"[fake:{purpose}] {user[:120]}"
        return Completion(text=text, model="fake-1", input_tokens=len(user) // 4, output_tokens=len(text) // 4)

    def embed(self, texts, *, purpose):
        out = []
        for t in texts:
            h = hashlib.sha256(t.encode()).digest()
            # spread 32 bytes across 1536 dims deterministically, then L2-normalise
            vec = [((h[i % 32] ^ (i * 31 & 0xFF)) / 255.0) - 0.5 for i in range(self.DIM)]
            norm = sum(v * v for v in vec) ** 0.5 or 1.0
            out.append([v / norm for v in vec])
        return out
