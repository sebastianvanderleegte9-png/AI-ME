from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date


@dataclass
class MetricPoint:
    date: date
    name: str
    value: float
    source: str
    job_platform_ref: str | None = None


class MetricsSource(ABC):
    """Non-social metric sources: search (Search Console), site signups, pages indexed.
    Social post metrics come through Social.stats(); this covers everything else."""

    @abstractmethod
    def pull(self, *, company_id: str, since: date, until: date) -> list[MetricPoint]: ...


class FakeMetricsSource(MetricsSource):
    def pull(self, *, company_id, since, until):
        out: list[MetricPoint] = []
        d = since
        i = 0
        while d <= until:
            out.append(MetricPoint(d, "search_impressions", 120 + i * 7, "fake:search_console"))
            out.append(MetricPoint(d, "pages_indexed", 3 + i // 3, "fake:search_console"))
            out.append(MetricPoint(d, "signups", 2 + (i % 3), "fake:signup_widget"))
            d = d.fromordinal(d.toordinal() + 1)
            i += 1
        return out
