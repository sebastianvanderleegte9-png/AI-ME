"""Every text the founder receives. Short, plain, numbered when there is a choice.
SMS is ~160 chars a segment; a message stays under ~600 (4 segments) unless it's a draft."""
from ..models import Job, Launch, Meeting, Relationship, Tool
from zoneinfo import ZoneInfo

MAX_DRAFT = 1100   # a LinkedIn post fits; longer text gets a link


def _clip(t: str, n: int) -> str:
    t = " ".join((t or "").split())   # one line: brief titles must not carry a draft's line breaks
    return t if len(t) <= n else t[: n - 1].rstrip() + "…"


def verify(code: str) -> str:
    return f"Your marketing engineer here. Reply with this code to link your phone: {code}"


def welcome(name: str, setup_url: str) -> str:
    return (f"Linked. Hi {name.split()[0]}. Three things to know:\n"
            f"1. I never post without your yes.\n2. Once a week, send me a voice memo about what happened.\n"
            f"3. Every Friday I text you one number.\nFinish setup (connect LinkedIn/X, 5 min): {setup_url}")


def brief(name: str, items: list[dict], focus: str | None, memo_due: bool, meetings: list["Meeting"] | None = None, tz: str = "America/New_York") -> str:
    """items: [{n, kind, title, meta}] — numbered so 'yes 1 3' works. meetings: today's
    confirmed calls, shown first so the day is mapped before the approval list."""
    lines = [f"Morning{', ' + name.split()[0] if name else ''}."]
    if meetings:
        try:
            tzinfo = ZoneInfo(tz)
        except Exception:
            tzinfo = ZoneInfo("America/New_York")
        lines.append("On your calendar: " + "; ".join(
            f"{m.confirmed_start.astimezone(tzinfo).strftime('%-I:%M%p').lower()} {m.subject} ({m.prospect_name or m.prospect_email})" for m in meetings))
    lines.append(f"{len(items)} for today:" if items else "Nothing else needs you today.")
    for it in items:
        lines.append(f"{it['n']}. {it['title']}{(' — ' + it['meta']) if it.get('meta') else ''}")
    if items:
        lines.append("Reply: yes (all) · yes 1 3 · no 2 · or a number to see it")
    if memo_due:
        lines.append("When you have 15 min: send a voice memo about this week.")
    if focus:
        lines.append(f"This week's focus: {focus}.")
    return "\n".join(lines)


def draft(j: Job, n: int | None = None, link: str | None = None) -> str:
    ch = {"linkedin": "LinkedIn", "x": "X"}.get(j.channel or "", j.channel or "")
    when = j.scheduled_for.strftime("%a %-I%p").lower() if j.scheduled_for else "next slot"
    head = f"{f'#{n} · ' if n else ''}{ch} · {when} · {(j.format or '').replace('_', ' ')}"
    body = (j.output or {}).get("text", "")
    if len(body) > MAX_DRAFT and link:
        body = _clip(body, MAX_DRAFT - 40) + f"\nfull: {link}"
    return f"{head}\n\n{body}\n\nyes / no / or text the fix"


def reply_target(j: Job, n: int | None = None) -> str:
    i = j.input or {}
    return (f"{f'#{n} · ' if n else ''}Reply to @{i.get('handle')} ({i.get('cluster')}) on {j.channel}\n"
            f"Their post: {_clip(i.get('post_text', ''), 160)}\n\nYour reply: {(j.output or {}).get('text', '')}\n\nyes / no / or text the fix")


def launch_task(j: Job, n: int | None = None) -> str:
    i = j.input or {}
    return f"{f'#{n} · ' if n else ''}Launch T{i.get('day', 0):+d}: {i.get('title')}\n{_clip(i.get('detail', ''), 240)}\n\nReply done when it's done."


def site_change(j: Job, n: int | None = None) -> str:
    i = j.input or {}
    cur = f"\nNow: {_clip(i.get('current') or '(none)', 120)}" if i.get("current") else ""
    return f"{f'#{n} · ' if n else ''}Site fix · {i.get('label')}{cur}\nProposed: {_clip((j.output or {}).get('text', ''), 400)}\nWhy: {i.get('why', '')}\n\nyes / no / or text the fix"


def tool_ideas(tools: list[Tool]) -> str:
    lines = ["3 free tools I can build for your buyers:"]
    for k, t in enumerate(tools[:3], 1):
        lines.append(f"{k}. {t.name} — {_clip(t.spec.get('question', ''), 90)}")
    lines.append("Reply build 1, 2 or 3. Or skip.")
    return "\n".join(lines)


def joint(rel: Relationship, partner_name: str) -> str:
    p = rel.plan or {}
    return (f"Joint launch idea: {partner_name} is on the platform. {rel.reason}.\n"
            f"Hook: \"{p.get('hook', '')}\"\nDate: {p.get('proposed_date')}\n\nyes to propose / no")


def friday(company: str, r: dict, launches: list[dict] | None = None) -> str:
    t, p = r["this"], r["prev"]
    def pct(a, b):
        return "first week" if not b else f"{(a - b) / b * 100:+.0f}% vs last week"
    top = r.get("top_posts") or []
    appr = f"{r['approval_rate']:.0%}" if r.get("approval_rate") is not None else "—"
    lines = [f"{t['impressions_icp']:,} impressions inside your ICP this week ({pct(t['impressions_icp'], p['impressions_icp'])}).",
             f"{t['signups']} signups · {t['impressions']:,} impressions overall · you approved {appr} of {r.get('decided', 0)} drafts."]
    if top:
        lines.append(f"Best post: \"{_clip(top[0]['text'], 80)}\" ({top[0]['impressions_icp']:,} in ICP).")
    src = r.get("signup_sources") or {}
    if src:
        lines.append("Signups came from: " + ", ".join(f"{k} {v}" for k, v in src.items()) + ".")
    for L in launches or []:
        lines.append(f"Launch '{L['name']}': {L['days_out']:+d} days, {L['status']}.")
    lines.append("Reply why for how the number is computed, or plan for next week.")
    return "\n".join(lines)


def meeting_decision(m: "Meeting") -> str:
    from datetime import datetime
    s = datetime.fromisoformat(m.chosen_slot["start"])
    return (f"{m.prospect_name or m.prospect_email} picked {s.strftime('%a %b %-d, %-I:%M%p')} for \"{m.subject}\". "
            f"yes to confirm (adds it to your calendar and theirs) / no to send other times.")


def meeting_confirmed(m: "Meeting", tz: str) -> str:
    try:
        tzinfo = ZoneInfo(tz)
    except Exception:
        tzinfo = ZoneInfo("America/New_York")
    s = m.confirmed_start.astimezone(tzinfo)
    return f"Confirmed with {m.prospect_name or m.prospect_email}: {s.strftime('%a %b %-d, %-I:%M%p')}. On your calendar."


def why() -> str:
    return ("Impressions inside ICP = a post's impressions × the share of people who engaged with it that match your buyer profile "
            "(the attention map). When fewer than 5 engaged accounts are visible I use a conservative 20% and say so. "
            "Not followers, not likes: only views from people who look like your customers.")


def plan(week: dict) -> str:
    lines = [f"This week ({week.get('week_start')}): focus on {week.get('focus') or 'the plan'}."]
    for d in (week.get("decisions") or [])[:4]:
        lines.append(f"• {d.get('reason')}")
    lines.append("Reply change to override (e.g. 'change: 3 posts, no replies').")
    return "\n".join(lines)


def memo_ack(claims: int, created: int, first_at: str | None) -> str:
    return (f"Got it — pulled {claims} things from that. {created} drafts coming through the day"
            f"{f', first at {first_at}' if first_at else ''}. Reply to each with yes, no, or the fix.")


def ack(what: str) -> str:
    return what


def clarify(options: list[str]) -> str:
    return "Not sure what that refers to. " + " · ".join(options)


def nothing_pending() -> str:
    return "Nothing waiting on you. Send a voice memo when you have 15 minutes, or text 'brief' for today's list."


HELP = ("Commands: brief · memo (then send audio) · yes / no / skip · yes 1 3 / no 2 · done · build 1 · why · plan · "
        "change: … · pause / resume · help. Anything else I treat as an edit to the last draft.")
