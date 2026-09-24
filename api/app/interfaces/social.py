from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
import uuid


@dataclass
class PublishResult:
    platform_ref: str
    url: str | None = None
    published_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class PostStats:
    platform_ref: str
    impressions: int = 0
    reactions: int = 0
    comments: int = 0
    reposts: int = 0
    clicks: int = 0
    engaged_handles: list[str] = field(default_factory=list)  # used for impressions-inside-ICP


class Social(ABC):
    """Publishing and per-post analytics on the founder's own accounts.

    Rules baked into every implementation:
      - official APIs only, founder-authorised OAuth tokens only
      - publish() is only ever called with a Job in state 'approved' or 'edited'
      - never operate an account the founder does not control
    """

    @abstractmethod
    def publish(self, *, founder_id: str, channel: str, text: str, media: list[dict] | None = None,
                reply_to_ref: str | None = None) -> PublishResult: ...

    @abstractmethod
    def stats(self, *, founder_id: str, channel: str, platform_ref: str) -> PostStats: ...

    @abstractmethod
    def account_stats(self, *, founder_id: str, channel: str) -> dict: ...

    @abstractmethod
    def recent_posts(self, *, channel: str, handle: str, limit: int = 10) -> list[dict]:
        """Public recent posts by any account: [{ref, text, posted_at, replies, reactions}].
        Used by the attention map to find live threads the ICP is reading."""
        ...


class FakeSocial(Social):
    """Records publishes in memory and returns plausible stats. Deterministic enough for tests."""

    TOPICS = ["hiring a marketing engineer", "why our onboarding failed", "pSEO for B2B", "founder-led sales",
              "AI agents in real estate", "what we learned shipping to 1,000 users", "the algo changed again",
              "compliance review took nine weeks", "launch day retro", "outbound is dead, again"]

    def recent_posts(self, *, channel, handle, limit=10):
        seed = sum(handle.encode())
        out = []
        for i in range(limit):
            k = (seed + i) % len(self.TOPICS)
            out.append({"ref": f"{channel}:{handle}:{i}", "text": f"{self.TOPICS[k]} — a thread by @{handle}",
                        "posted_at": f"2026-09-{max(1, 24 - i):02d}T09:00:00Z",
                        "replies": (seed * (i + 1)) % 40, "reactions": (seed * (i + 3)) % 300})
        return out

    def __init__(self):
        self.published: list[dict] = []

    def publish(self, *, founder_id, channel, text, media=None, reply_to_ref=None):
        ref = f"fake-{channel}-{uuid.uuid4().hex[:10]}"
        self.published.append({"founder_id": founder_id, "channel": channel, "text": text,
                               "media": media or [], "reply_to_ref": reply_to_ref, "ref": ref})
        return PublishResult(platform_ref=ref, url=f"https://{channel}.example/{ref}")

    def stats(self, *, founder_id, channel, platform_ref):
        n = sum(platform_ref.encode()) % 900 + 100
        return PostStats(platform_ref=platform_ref, impressions=n * 10, reactions=n // 10,
                         comments=n // 40, reposts=n // 80, clicks=n // 20,
                         engaged_handles=[f"engaged_{i}" for i in range(n // 100)])

    def account_stats(self, *, founder_id, channel):
        return {"followers": 2500, "impressions_30d": 40000, "posts_30d": 8,
                "recent_posts": [
                    {"text": f"fake past post {i} on {channel}: shipped a thing, learned a thing.",
                     "impressions": 1000 + i * 137, "reactions": 20 + i} for i in range(5)]}
