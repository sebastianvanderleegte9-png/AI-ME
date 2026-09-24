"""Real providers: Twilio for SMS/MMS, OpenAI Whisper (or any compatible endpoint) for voice memos.
Selected by MESSAGING_PROVIDER=twilio / TRANSCRIPTION_PROVIDER=whisper."""
import base64
import hashlib
import hmac

import httpx

from .messaging import InboundMessage, Messaging, SentMessage, Transcription


class TwilioMessaging(Messaging):
    def __init__(self, account_sid: str, auth_token: str, from_number: str):
        self.sid, self.token, self.from_number = account_sid, auth_token, from_number
        self._client = httpx.Client(auth=(account_sid, auth_token), timeout=20)

    def send(self, *, to, body):
        r = self._client.post(f"https://api.twilio.com/2010-04-01/Accounts/{self.sid}/Messages.json",
                              data={"To": to, "From": self.from_number, "Body": body})
        r.raise_for_status()
        j = r.json()
        return SentMessage(provider_ref=j["sid"], segments=int(j.get("num_segments") or 1))

    def parse_inbound(self, payload):
        n = int(payload.get("NumMedia", 0) or 0)
        return InboundMessage(from_phone=payload.get("From", ""), body=payload.get("Body", "") or "",
                              media=[{"url": payload[f"MediaUrl{i}"], "content_type": payload.get(f"MediaContentType{i}", "")} for i in range(n)],
                              provider_ref=payload.get("MessageSid"))

    def verify_signature(self, headers, url, payload):
        sig = headers.get("x-twilio-signature") or headers.get("X-Twilio-Signature", "")
        s = url + "".join(k + str(payload[k]) for k in sorted(payload))
        expected = base64.b64encode(hmac.new(self.token.encode(), s.encode(), hashlib.sha1).digest()).decode()
        return hmac.compare_digest(sig, expected)

    def fetch_media(self, url: str) -> bytes:
        return self._client.get(url, follow_redirects=True).content


class WhisperTranscription(Transcription):
    def __init__(self, api_key: str, fetch):
        self.key, self.fetch = api_key, fetch

    def transcribe(self, *, media_url, content_type):
        audio = self.fetch(media_url)
        ext = {"audio/ogg": "ogg", "audio/mpeg": "mp3", "audio/mp4": "m4a", "audio/amr": "amr", "audio/x-m4a": "m4a"}.get(content_type, "ogg")
        r = httpx.post("https://api.openai.com/v1/audio/transcriptions", headers={"Authorization": f"Bearer {self.key}"},
                       files={"file": (f"memo.{ext}", audio, content_type)}, data={"model": "whisper-1"}, timeout=120)
        r.raise_for_status()
        return r.json()["text"]
