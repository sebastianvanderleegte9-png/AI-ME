"""Calendar and email behind interfaces with fakes (Component 15). Both act on the founder's
own Outlook account through the token Component 14's OAuth flow already stores encrypted —
this module never sees a plaintext credential; the caller hands it a decrypted access token."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime

import httpx

GRAPH = "https://graph.microsoft.com/v1.0"


@dataclass
class FreeBusyBlock:
    start: datetime
    end: datetime


@dataclass
class CalendarEvent:
    event_ref: str
    subject: str
    start: datetime
    end: datetime


class Calendar(ABC):
    @abstractmethod
    def free_busy(self, access_token: str, start: datetime, end: datetime) -> list[FreeBusyBlock]: ...

    @abstractmethod
    def create_event(self, access_token: str, *, subject: str, start: datetime, end: datetime,
                     attendee_email: str, attendee_name: str | None, body: str) -> CalendarEvent: ...

    @abstractmethod
    def events_on(self, access_token: str, day: datetime) -> list[CalendarEvent]: ...


class FakeCalendar(Calendar):
    """Keyed by access token so a test can seed busy blocks and read back created events
    without a real Outlook account."""
    def __init__(self):
        self.busy: dict[str, list[FreeBusyBlock]] = {}
        self.events: dict[str, list[CalendarEvent]] = {}

    def free_busy(self, access_token, start, end):
        return [b for b in self.busy.get(access_token, []) if b.start < end and b.end > start]

    def create_event(self, access_token, *, subject, start, end, attendee_email, attendee_name, body):
        ev = CalendarEvent(event_ref=f"evt_fake_{len(self.events.get(access_token, [])) + 1}", subject=subject, start=start, end=end)
        self.events.setdefault(access_token, []).append(ev)
        self.busy.setdefault(access_token, []).append(FreeBusyBlock(start, end))
        return ev

    def events_on(self, access_token, day):
        return [e for e in self.events.get(access_token, []) if e.start.date() == day.date()]


class MicrosoftGraphCalendar(Calendar):
    def _h(self, token):
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Prefer": 'outlook.timezone="UTC"'}

    def free_busy(self, access_token, start, end):
        r = httpx.get(f"{GRAPH}/me/calendarview", headers=self._h(access_token),
                     params={"startDateTime": start.isoformat(), "endDateTime": end.isoformat(), "$select": "start,end"}, timeout=20)
        r.raise_for_status()
        return [FreeBusyBlock(datetime.fromisoformat(e["start"]["dateTime"]), datetime.fromisoformat(e["end"]["dateTime"]))
                for e in r.json().get("value", [])]

    def create_event(self, access_token, *, subject, start, end, attendee_email, attendee_name, body):
        payload = {"subject": subject, "body": {"contentType": "HTML", "content": body},
                   "start": {"dateTime": start.isoformat(), "timeZone": "UTC"}, "end": {"dateTime": end.isoformat(), "timeZone": "UTC"},
                   "attendees": [{"emailAddress": {"address": attendee_email, "name": attendee_name or attendee_email}, "type": "required"}]}
        r = httpx.post(f"{GRAPH}/me/events", headers=self._h(access_token), json=payload, timeout=20)
        r.raise_for_status()
        j = r.json()
        return CalendarEvent(event_ref=j["id"], subject=subject, start=start, end=end)

    def events_on(self, access_token, day):
        start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        end = day.replace(hour=23, minute=59, second=59, microsecond=0)
        r = httpx.get(f"{GRAPH}/me/calendarview", headers=self._h(access_token),
                     params={"startDateTime": start.isoformat(), "endDateTime": end.isoformat()}, timeout=20)
        r.raise_for_status()
        return [CalendarEvent(e["id"], e.get("subject", ""), datetime.fromisoformat(e["start"]["dateTime"]),
                              datetime.fromisoformat(e["end"]["dateTime"])) for e in r.json().get("value", [])]


@dataclass
class EmailResult:
    message_ref: str


class Email(ABC):
    @abstractmethod
    def send(self, access_token: str, *, from_name: str, to_email: str, to_name: str | None, subject: str, body_html: str) -> EmailResult: ...


class FakeEmail(Email):
    def __init__(self):
        self.sent: list[dict] = []

    def send(self, access_token, *, from_name, to_email, to_name, subject, body_html):
        ref = f"msg_fake_{len(self.sent) + 1}"
        self.sent.append({"ref": ref, "to": to_email, "subject": subject, "body": body_html})
        return EmailResult(message_ref=ref)


class MicrosoftGraphEmail(Email):
    def send(self, access_token, *, from_name, to_email, to_name, subject, body_html):
        payload = {"message": {"subject": subject, "body": {"contentType": "HTML", "content": body_html},
                               "toRecipients": [{"emailAddress": {"address": to_email, "name": to_name or to_email}}]},
                  "saveToSentItems": True}
        r = httpx.post(f"{GRAPH}/me/sendMail", headers={"Authorization": f"Bearer {access_token}"}, json=payload, timeout=20)
        r.raise_for_status()
        return EmailResult(message_ref=r.headers.get("request-id", "sent"))
