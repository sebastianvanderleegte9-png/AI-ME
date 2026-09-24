"""Real LLM provider. Model names are pinned here, per purpose, so a change is a
versioned deploy (Principle: model governance)."""
import hashlib
import json

from .llm import LLM, Completion

MODELS = {
    "default": "claude-sonnet-4-5",
    "product_summary": "claude-sonnet-4-5",
    "icp": "claude-sonnet-4-5",
    "voice_draft": "claude-sonnet-4-5",
    "scorecard_narrative": "claude-sonnet-4-5",
}


class AnthropicLLM(LLM):
    FAKE_EMBEDDINGS = True   # until a real embedding provider is wired (see embed())

    def __init__(self, api_key: str):
        import anthropic
        self._client = anthropic.Anthropic(api_key=api_key)

    def complete(self, system, user, *, purpose, model=None, temperature=0.4, max_tokens=1024, json_mode=False):
        model = model or MODELS.get(purpose, MODELS["default"])
        sys_prompt = system
        if json_mode:
            sys_prompt += "\n\nRespond with a single JSON object and nothing else. No markdown fences."
        resp = self._client.messages.create(
            model=model, max_tokens=max_tokens, temperature=temperature,
            system=sys_prompt, messages=[{"role": "user", "content": user}])
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
        if json_mode and text.startswith("```"):
            text = text.strip("`")
            text = text[text.find("{"):text.rfind("}") + 1]
        return Completion(text=text, model=model,
                          input_tokens=resp.usage.input_tokens, output_tokens=resp.usage.output_tokens)

    def embed(self, texts, *, purpose):
        # Anthropic does not ship an embeddings endpoint. Until a dedicated embedding
        # provider is added (Component 4 needs one for the attention map at scale), use a
        # deterministic hashed bag-of-words projection: identical texts -> identical vectors,
        # texts sharing vocabulary -> higher cosine. Good enough for intake sanity checks.
        dim = 1536
        out = []
        for t in texts:
            vec = [0.0] * dim
            for tok in t.lower().split():
                h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
                vec[h % dim] += 1.0 if (h >> 8) % 2 else -1.0
            norm = sum(v * v for v in vec) ** 0.5 or 1.0
            out.append([v / norm for v in vec])
        return out
