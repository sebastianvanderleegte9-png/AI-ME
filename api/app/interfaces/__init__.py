"""The four seams between the product and the outside world.

Every component talks to these abstract classes, never to a vendor SDK directly.
Each has a Fake implementation so the whole system runs with no external accounts,
and so tests are deterministic. Real implementations arrive with the component that
needs them (Anthropic LLM in Component 1, LinkedIn/X in Component 3, etc.).
"""
from .enrichment import Enrichment, FakeEnrichment
from .llm import LLM, FakeLLM
from .metrics import FakeMetricsSource, MetricsSource
from .social import FakeSocial, Social
from .registry import get_enrichment, get_llm, get_messaging, get_metrics_source, get_social, get_transcription, get_billing, get_oauth, get_calendar, get_email

__all__ = [
    "LLM", "FakeLLM", "Enrichment", "FakeEnrichment", "Social", "FakeSocial",
    "MetricsSource", "FakeMetricsSource",
    "get_llm", "get_enrichment", "get_social", "get_metrics_source", "get_messaging", "get_transcription", "get_billing", "get_oauth", "get_calendar", "get_email",
]
