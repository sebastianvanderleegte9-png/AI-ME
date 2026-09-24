"""Meeting scheduling over the founder's own Outlook (Component 15).

propose() finds open slots (real free/busy if Outlook is connected, business-hours otherwise),
emails the prospect from the founder's own address, and waits. The prospect picks a time on a
public booking page with no login. That puts the meeting in `awaiting_founder`: only then does
the founder get a text, and only a yes from the founder creates the calendar event and confirms
it — the bot never books anything on its own. A no regenerates times and re-emails automatically,
so the founder doesn't have to babysit the back-and-forth."""
from datetime import datetime, timedelta, timezone
import secrets
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from ..interfaces import get_calendar, get_email, get_llm
from ..interfaces.tokens import access_token
from ..models import Company, Founder, Job, Meeting
from ..settings import settings

BUSINESS_HOURS = (10, 13, 16)   # local candidate start hours
DEFAULT_DURATION = 30

EMAIL_SYS = """You write a short, warm scheduling email AS the founder, in plain language, to someone who
has shown interest in talking. State the reason for the call in one line using the context given, offer
the three times listed (already formatted, keep them exactly as given), and mention they can pick another
time at the booking link if none work. No pitch, no flattery, under 120 words. Output the email body only,
no subject line."""


def _tz(f: Founder) -> ZoneInfo:
    try:
        return ZoneInfo(f.timezone or "America/New_York")
    except Exception:
        return ZoneInfo("America/New_York")


def slots_for(db: Session, founder: Founder, *, count: int = 3, duration_minutes: int = DEFAULT_DURATION,
             days_ahead: int = 10) -> list[tuple[datetime, datetime]]:
    tzinfo = _tz(founder)
    now_local = datetime.now(tzinfo)
    token = access_token(db, founder.id, "outlook")
    busy = []
    if token:
        cal = get_calendar()
        busy = cal.free_busy(token, now_local.astimezone(timezone.utc), (now_local + timedelta(days=days_ahead)).astimezone(timezone.utc))
    out: list[tuple[datetime, datetime]] = []
    for offset in range(days_ahead):
        d = (now_local + timedelta(days=offset)).date()
        if d.weekday() >= 5:
            continue
        for hour in BUSINESS_HOURS:
            s_local = datetime(d.year, d.month, d.day, hour, 0, tzinfo=tzinfo)
            if s_local <= now_local + timedelta(hours=2):
                continue
            e_local = s_local + timedelta(minutes=duration_minutes)
            s_utc, e_utc = s_local.astimezone(timezone.utc), e_local.astimezone(timezone.utc)
            if any(b.start < e_utc and b.end > s_utc for b in busy):
                continue
            out.append((s_utc, e_utc))
            if len(out) >= count:
                return out
    return out


def _fmt(dt: datetime, tzinfo: ZoneInfo) -> str:
    return dt.astimezone(tzinfo).strftime("%a %b %-d, %-I:%M%p")


def _fake_email(founder_name: str, subject: str, slot_lines: list[str], booking_url: str, context: str) -> str:
    return (f"Hi — following up on {context or 'our conversation'}. Would one of these work for a quick call?\n\n"
            + "\n".join(f"- {s}" for s in slot_lines) +
            f"\n\nIf none of those work, pick another time here: {booking_url}\n\n{founder_name}")


def _send_slots(db: Session, company: Company, founder: Founder, meeting: Meeting, slots: list[tuple[datetime, datetime]], context: str) -> None:
    tzinfo = _tz(founder)
    booking_url = f"{settings.public_base_url}/book/{meeting.booking_token}"
    meeting.proposed_slots = [{"start": s.isoformat(), "end": e.isoformat()} for s, e in slots]
    lines = [_fmt(s, tzinfo) for s, _ in slots]
    llm = get_llm()
    body = llm.complete(EMAIL_SYS, f"Founder: {founder.name}\nSubject: {meeting.subject}\nContext: {context}\nTimes:\n" + "\n".join(lines) +
                        f"\nBooking link: {booking_url}", purpose="meeting_email", temperature=0.5, max_tokens=300).text.strip()
    if body.startswith("[fake:"):
        body = _fake_email(founder.name, meeting.subject, lines, booking_url, context)
    token = access_token(db, founder.id, "outlook")
    if not token:
        meeting.state = "blocked"
        db.commit()
        return
    html = body.replace("\n", "<br>")
    get_email().send(token, from_name=founder.name, to_email=meeting.prospect_email, to_name=meeting.prospect_name,
                     subject=meeting.subject, body_html=html)
    meeting.state = "sent"
    db.commit()


def propose(db: Session, company: Company, founder: Founder, *, prospect_name: str, prospect_email: str, subject: str,
           context: str = "", job: Job | None = None, relationship_id=None, duration_minutes: int = DEFAULT_DURATION) -> Meeting:
    slots = slots_for(db, founder, duration_minutes=duration_minutes)
    meeting = Meeting(company_id=company.id, founder_id=founder.id, job_id=job.id if job else None, relationship_id=relationship_id,
                      prospect_name=prospect_name, prospect_email=prospect_email, subject=subject, duration_minutes=duration_minutes,
                      booking_token=secrets.token_urlsafe(20))
    db.add(meeting)
    db.flush()
    if not slots:
        meeting.state = "blocked"
        db.commit()
        return meeting
    _send_slots(db, company, founder, meeting, slots, context)
    db.refresh(meeting)
    return meeting


def by_token(db: Session, token: str) -> Meeting | None:
    from sqlalchemy import select
    return db.scalars(select(Meeting).where(Meeting.booking_token == token)).first()


def choose_slot(db: Session, meeting: Meeting, index: int) -> Meeting:
    if meeting.state not in ("sent",) or not (0 <= index < len(meeting.proposed_slots or [])):
        raise ValueError("that link has already been used or the time is no longer offered")
    meeting.chosen_slot = meeting.proposed_slots[index]
    meeting.state = "awaiting_founder"
    db.commit()
    db.refresh(meeting)
    from ..sms.engine import send_meeting_decision
    founder = db.get(Founder, meeting.founder_id)
    send_meeting_decision(db, founder, meeting)
    return meeting


def confirm(db: Session, meeting: Meeting) -> Meeting:
    founder = db.get(Founder, meeting.founder_id)
    tzinfo = _tz(founder)
    start = datetime.fromisoformat(meeting.chosen_slot["start"])
    end = datetime.fromisoformat(meeting.chosen_slot["end"])
    token = access_token(db, founder.id, "outlook")
    if token:
        ev = get_calendar().create_event(token, subject=meeting.subject, start=start, end=end,
                                         attendee_email=meeting.prospect_email, attendee_name=meeting.prospect_name,
                                         body=f"Booked by {founder.name} via Aime.")
        meeting.calendar_event_ref = ev.event_ref
        get_email().send(token, from_name=founder.name, to_email=meeting.prospect_email, to_name=meeting.prospect_name,
                         subject=f"Confirmed: {meeting.subject}", body_html=f"Confirmed for {_fmt(start, tzinfo)} ({founder.timezone}). See you then.")
    else:
        meeting.calendar_event_ref = f"internal-{meeting.id.hex[:8]}"
    meeting.confirmed_start, meeting.confirmed_end, meeting.state = start, end, "confirmed"
    db.commit()
    db.refresh(meeting)
    return meeting


def decline_and_reschedule(db: Session, meeting: Meeting) -> Meeting:
    """The founder said no to the picked time. Try again automatically rather than making
    them chase the prospect: fresh slots, excluding the one just declined, re-emailed."""
    founder = db.get(Founder, meeting.founder_id)
    company = db.get(Company, meeting.company_id)
    declined_start = meeting.chosen_slot.get("start") if meeting.chosen_slot else None
    meeting.chosen_slot, meeting.rounds = None, meeting.rounds + 1
    count = len(meeting.proposed_slots) or 3
    pool = slots_for(db, founder, count=count + 1, duration_minutes=meeting.duration_minutes)
    slots = [s for s in pool if s[0].isoformat() != declined_start][:count]
    if not slots or meeting.rounds > 3:
        meeting.state = "declined"
        db.commit()
        return meeting
    _send_slots(db, company, founder, meeting, slots, context=f"rescheduling {meeting.subject}")
    db.refresh(meeting)
    return meeting


def today_confirmed(db: Session, founder: Founder, day: datetime | None = None) -> list[Meeting]:
    from sqlalchemy import select
    tzinfo = _tz(founder)
    d = (day or datetime.now(tzinfo)).date()
    rows = db.scalars(select(Meeting).where(Meeting.founder_id == founder.id, Meeting.state == "confirmed",
                                            Meeting.confirmed_start.is_not(None))).all()
    return sorted([m for m in rows if m.confirmed_start.astimezone(tzinfo).date() == d], key=lambda m: m.confirmed_start)
