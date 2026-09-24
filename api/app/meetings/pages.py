"""The public booking page (Component 15). No login: the booking_token in the URL is the
only credential, same pattern as the setup wizard. Same dark theme as the rest of the site."""
from html import escape as e
from zoneinfo import ZoneInfo

from ..onboarding.pages import CSS as WIZARD_CSS
from ..onboarding.site import BRAND_CSS, font_link
from ..settings import settings


def _fmt(iso: str, tzinfo: ZoneInfo) -> str:
    from datetime import datetime
    return datetime.fromisoformat(iso).astimezone(tzinfo).strftime("%A %B %-d, %-I:%M%p")


def _shell(body: str) -> str:
    n = e(settings.site_name)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Book a time · {n}</title>{font_link()}<style>{BRAND_CSS}{WIZARD_CSS}</style></head><body><div class="wrap">
<div class="brand"><a href="/" style="color:inherit;text-decoration:none">{n}</a></div>
<div class="card">{body}</div></div></body></html>"""


def pick(meeting, founder_name: str, founder_tz: str) -> str:
    tzinfo = ZoneInfo(founder_tz or "America/New_York")
    opts = "".join(
        f'<form method="post" action="/book/{e(meeting.booking_token)}/{i}" style="margin-top:10px">'
        f'<button style="width:100%;text-align:left" class="btn ghost">{_fmt(s["start"], tzinfo)}</button></form>'
        for i, s in enumerate(meeting.proposed_slots or []))
    return _shell(f"""<h1>{e(meeting.subject)}</h1>
<p class="sub">A time with {e(founder_name)}. Pick whichever works — they'll get a text to confirm.</p>
{opts}
<p class="note">Times shown in {e(founder_tz)}.</p>""")


def picked(meeting, founder_name: str) -> str:
    return _shell(f"""<h1>Thanks — sent.</h1>
<p class="sub">{e(founder_name)} will confirm shortly. You'll get an email the moment it's on the calendar.</p>""")


def gone() -> str:
    return _shell("""<h1>This link has expired.</h1>
<p class="sub">Either a time was already picked, or new times have since been sent to your email. Check your inbox for the latest.</p>""")
