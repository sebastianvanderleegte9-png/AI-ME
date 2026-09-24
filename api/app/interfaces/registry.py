"""Provider selection from settings. Real providers register here as they are built:
  Component 1 -> AnthropicLLM, ApolloEnrichment
  Component 3 -> LinkedInXSocial
  Component 5 -> SearchConsoleMetrics
"""
from functools import lru_cache

from ..settings import settings
from .enrichment import Enrichment, FakeEnrichment
from .llm import LLM, FakeLLM
from .metrics import FakeMetricsSource, MetricsSource
from .social import FakeSocial, Social


@lru_cache
def get_llm() -> LLM:
    if settings.llm_provider == "fake":
        return FakeLLM()
    raise NotImplementedError(f"llm_provider={settings.llm_provider} arrives in Component 1")


@lru_cache
def get_enrichment() -> Enrichment:
    if settings.enrichment_provider == "fake":
        return FakeEnrichment()
    raise NotImplementedError(f"enrichment_provider={settings.enrichment_provider} arrives in Component 1")


@lru_cache
def get_social() -> Social:
    if settings.social_provider == "fake":
        return FakeSocial()
    raise NotImplementedError(f"social_provider={settings.social_provider} arrives in Component 3")


@lru_cache
def get_metrics_source() -> MetricsSource:
    return FakeMetricsSource()
