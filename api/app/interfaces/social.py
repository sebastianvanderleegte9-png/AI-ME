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


class FakeSocial(Social):
    """Records publishes in memory and returns plausible stats. Deterministic enough for tests."""

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
        return {"followers": 2500, "impressions_30d": 40000, "posts_30d": 8}
