from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class Person:
    handle: str
    platform: str
    name: str | None = None
    headline: str | None = None
    org: str | None = None
    org_domain: str | None = None
    role: str | None = None
    follows_count: int | None = None
    raw: dict = field(default_factory=dict)


@dataclass
class Org:
    domain: str
    name: str | None = None
    industry: str | None = None
    employees: int | None = None
    stage: str | None = None
    description: str | None = None
    raw: dict = field(default_factory=dict)


class Enrichment(ABC):
    """People and company data for the ICP model and the attention map.
    Uses licensed vendor data and public profiles only."""

    @abstractmethod
    def person(self, handle: str, platform: str) -> Person | None: ...

    @abstractmethod
    def org(self, domain: str) -> Org | None: ...

    @abstractmethod
    def search_people(self, query: str, platform: str, limit: int = 50) -> list[Person]: ...


class FakeEnrichment(Enrichment):
    def person(self, handle, platform):
        return Person(handle=handle, platform=platform, name=handle.title(),
                      headline=f"Fake headline for {handle}", org="FakeCo", org_domain="fakeco.example",
                      role="Founder", follows_count=1234)

    def org(self, domain):
        return Org(domain=domain, name=domain.split(".")[0].title(), industry="Software",
                   employees=25, stage="seed", description=f"Fake description for {domain}")

    def search_people(self, query, platform, limit=50):
        return [Person(handle=f"{query.replace(' ', '_')}_{i}", platform=platform,
                       headline=f"{query} #{i}", org=f"Org{i}", role="VP Sales" if i % 2 else "Founder")
                for i in range(min(limit, 10))]
