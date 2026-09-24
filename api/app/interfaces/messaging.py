"""Messaging and transcription (Component 13). Twilio and Whisper are the real providers;
fakes record and return deterministically."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import uuid


@dataclass
class SentMessage:
    provider_ref: str
    segments: int = 1


@dataclass
class InboundMessage:
    from_phone: str
    body: str
    media: list[dict] = field(default_factory=list)   # [{url, content_type}]
    provider_ref: str | None = None


class Messaging(ABC):
    @abstractmethod
    def send(self, *, to: str, body: str) -> SentMessage: ...

    @abstractmethod
    def parse_inbound(self, payload: dict) -> InboundMessage:
        """Provider webhook payload -> InboundMessage."""
        ...

    @abstractmethod
    def verify_signature(self, headers: dict, url: str, payload: dict) -> bool: ...


class Transcription(ABC):
    @abstractmethod
    def transcribe(self, *, media_url: str, content_type: str) -> str: ...


class FakeMessaging(Messaging):
    def __init__(self):
        self.sent: list[dict] = []

    def send(self, *, to, body):
        ref = f"fake-sms-{uuid.uuid4().hex[:8]}"
        self.sent.append({"to": to, "body": body, "ref": ref})
        return SentMessage(provider_ref=ref, segments=max(1, (len(body) + 159) // 160))

    def parse_inbound(self, payload):
        return InboundMessage(from_phone=payload.get("From", ""), body=payload.get("Body", "") or "",
                              media=[{"url": payload[f"MediaUrl{i}"], "content_type": payload.get(f"MediaContentType{i}", "audio/ogg")}
                                     for i in range(int(payload.get("NumMedia", 0) or 0)) if payload.get(f"MediaUrl{i}")],
                              provider_ref=payload.get("MessageSid"))

    def verify_signature(self, headers, url, payload):
        return True


class FakeTranscription(Transcription):
    """Returns the text hidden in the fake media url (tests put it there), else a stock memo."""
    def transcribe(self, *, media_url, content_type):
        if "text=" in media_url:
            from urllib.parse import parse_qs, urlparse
            return parse_qs(urlparse(media_url).query).get("text", [""])[0]
        return ("This week we shipped the packet feature to the Florida agents. One agent told me she saved four hours. "
                "We got the onboarding wrong the first time; half never finished the video. I think most brokerages are wrong about AI.")
