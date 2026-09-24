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
    if settings.llm_provider == "anthropic":
        from .anthropic_llm import AnthropicLLM
        if not settings.anthropic_api_key:
            raise RuntimeError("LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is not set")
        return AnthropicLLM(settings.anthropic_api_key)
    raise NotImplementedError(f"unknown llm_provider={settings.llm_provider}")


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


@lru_cache
def get_messaging():
    from .messaging import FakeMessaging
    if settings.messaging_provider == "fake":
        return FakeMessaging()
    if settings.messaging_provider == "twilio":
        from .twilio_messaging import TwilioMessaging
        if not (settings.twilio_account_sid and settings.twilio_auth_token and settings.twilio_from_number):
            raise RuntimeError("MESSAGING_PROVIDER=twilio needs TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER")
        return TwilioMessaging(settings.twilio_account_sid, settings.twilio_auth_token, settings.twilio_from_number)
    raise NotImplementedError(settings.messaging_provider)


@lru_cache
def get_transcription():
    from .messaging import FakeTranscription
    if settings.transcription_provider == "fake":
        return FakeTranscription()
    if settings.transcription_provider == "whisper":
        from .twilio_messaging import WhisperTranscription
        if not settings.openai_api_key:
            raise RuntimeError("TRANSCRIPTION_PROVIDER=whisper needs OPENAI_API_KEY")
        m = get_messaging()
        return WhisperTranscription(settings.openai_api_key, getattr(m, "fetch_media", lambda u: b""))
    raise NotImplementedError(settings.transcription_provider)
