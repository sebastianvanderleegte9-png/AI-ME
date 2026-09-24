"""The SMS conversation (Component 13).

Outbound: every send is logged and, when it asks a question, sets `state.current` (what a
bare yes/no means) or `state.batch` (numbered items). Inbound: parse the reply against that
state and dispatch to the existing endpoints' logic — decisions on jobs, tool builds, joint
proposals, interviews from voice memos. Nothing here publishes; it only records decisions
the same way a tap in the app does."""
from datetime import datetime, timedelta, timezone
import random
import re
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..interfaces import get_messaging, get_transcription
from ..models import Company, Founder, Job, Launch, Meeting, Relationship, SmsMessage, SmsState, Tool
from ..settings import settings
from . import render

YES = {"yes", "y", "yep", "yeah", "ok", "okay", "approve", "go", "ship", "post", "send", "👍", "✅", "all", "yes all", "yes to all"}
NO = {"no", "n", "nope", "reject", "kill", "drop", "skip", "pass", "👎", "❌"}
DONE = {"done", "did it", "finished", "✓"}
LATER = {"later", "tomorrow", "not now", "hold"}


def _state(db: Session, f: Founder) -> SmsState:
    st = db.get(SmsState, f.id)
    if not st:
        st = SmsState(founder_id=f.id)
        db.add(st)
        db.flush()
    return st


def _log(db: Session, f: Founder | None, direction: str, phone: str, body: str, kind: str | None = None,
         refs: dict | None = None, media: list | None = None, provider_ref: str | None = None) -> SmsMessage:
    m = SmsMessage(founder_id=f.id if f else None, company_id=f.company_id if f else None, direction=direction, phone=phone,
                   body=body, kind=kind, refs=refs or {}, media=media or [], provider_ref=provider_ref)
    db.add(m)
    db.flush()
    return m


def send(db: Session, f: Founder, body: str, kind: str, refs: dict | None = None, *, current: dict | None = None,
         batch: list | None = None) -> SmsMessage:
    st = _state(db, f)
    if st.paused and kind not in ("verify", "ack"):
        return _log(db, f, "out", f.phone or "", body, kind="suppressed:" + kind, refs=refs)
    res = get_messaging().send(to=f.phone, body=body)
    m = _log(db, f, "out", f.phone, body, kind=kind, refs=refs, provider_ref=res.provider_ref)
    if current is not None:
        st.current = {**current, "sent_at": datetime.now(timezone.utc).isoformat(), "message_id": str(m.id)}
    if batch is not None:
        st.batch = batch
    db.commit()
    return m


# ---------- outbound: what we proactively send ----------
def start_verify(db: Session, f: Founder, phone: str) -> str:
    code = f"{random.randint(0, 999999):06d}"
    # a phone belongs to one founder: unlink it from any previous owner (they must re-verify to reclaim it)
    for other in db.scalars(select(Founder).where(Founder.phone == phone, Founder.id != f.id)):
        other.phone, other.phone_verified_at = None, None
    db.flush()
    f.phone = phone
    st = _state(db, f)
    st.pending_verify = code
    db.commit()
    send(db, f, render.verify(code), "verify")
    return code


def pending_items(db: Session, f: Founder, limit: int = 8) -> list[dict]:
    jobs = db.scalars(select(Job).where(Job.founder_id == f.id, Job.state == "pending",
                                        Job.type.in_(["post", "reply", "launch_task", "site_change", "outreach"]))
                      .order_by(Job.scheduled_for.nulls_last(), Job.created_at).limit(limit)).all()
    items = []
    for n, j in enumerate(jobs, 1):
        i = j.input or {}
        if j.type == "post":
            title, meta = f"Post ({j.channel}): {render._clip((j.output or {}).get('text', ''), 60)}", (j.format or "").replace("_", " ")
        elif j.type == "reply":
            title, meta = f"Reply to @{i.get('handle')}", j.channel
        elif j.type == "launch_task":
            title, meta = f"Launch: {i.get('title')}", f"T{i.get('day', 0):+d}"
        elif j.type == "site_change":
            title, meta = f"Site fix: {i.get('label')}", None
        elif j.channel == "email":
            title, meta = f"Email to {i.get('prospect_name') or i.get('prospect_email')}", i.get("prospect_company")
        else:
            title, meta = f"DM to @{i.get('handle')}", i.get("cluster")
        items.append({"n": n, "kind": j.type, "job_id": str(j.id), "title": title, "meta": meta})
    return items


def send_brief(db: Session, f: Founder) -> SmsMessage:
    items = pending_items(db, f)
    from ..meetings.engine import today_confirmed
    from ..models import Plan
    ws = (datetime.now(timezone.utc).date() - timedelta(days=datetime.now(timezone.utc).weekday()))
    p = db.scalars(select(Plan).where(Plan.company_id == f.company_id, Plan.week_start == ws)).first()
    focus = ((p.scorecard or {}).get("weekly") or {}).get("focus") if p else None
    last_memo = db.scalars(select(SmsMessage).where(SmsMessage.founder_id == f.id, SmsMessage.kind == "voice")
                           .order_by(SmsMessage.created_at.desc())).first()
    memo_due = not last_memo or (datetime.now(timezone.utc) - last_memo.created_at.replace(tzinfo=timezone.utc)) > timedelta(days=6)
    meetings = today_confirmed(db, f)
    return send(db, f, render.brief(f.name, items, focus, memo_due, meetings, f.timezone), "brief", {"job_ids": [i["job_id"] for i in items]},
                current={}, batch=items)


def send_item(db: Session, f: Founder, j: Job, n: int | None = None) -> SmsMessage:
    link = f"{settings.public_base_url}/jobs/{j.id}"
    body = {"post": lambda: render.draft(j, n, link), "reply": lambda: render.reply_target(j, n),
            "launch_task": lambda: render.launch_task(j, n), "site_change": lambda: render.site_change(j, n),
            "outreach": lambda: render.reply_target(j, n)}[j.type]()
    return send(db, f, body, j.type, {"job_ids": [str(j.id)]}, current={"kind": "job", "job_id": str(j.id)})


def send_tool_ideas(db: Session, f: Founder, tools: list[Tool]) -> SmsMessage:
    return send(db, f, render.tool_ideas(tools), "tool_ideas", {"tool_ids": [str(t.id) for t in tools]},
                current={"kind": "tools", "tool_ids": [str(t.id) for t in tools[:3]]})


def send_joint(db: Session, f: Founder, rel: Relationship) -> SmsMessage:
    partner = db.get(Company, rel.partner_company_id if rel.company_id == f.company_id else rel.company_id)
    return send(db, f, render.joint(rel, partner.name if partner else "a partner"), "joint", {"relationship_id": str(rel.id)},
                current={"kind": "joint", "relationship_id": str(rel.id)})


def send_meeting_decision(db: Session, f: Founder, meeting: Meeting) -> SmsMessage:
    return send(db, f, render.meeting_decision(meeting), "meeting", {"meeting_id": str(meeting.id)},
                current={"kind": "meeting", "meeting_id": str(meeting.id)})


def send_friday(db: Session, f: Founder) -> SmsMessage:
    from ..metrics.report import rollup
    c = db.get(Company, f.company_id)
    r = rollup(db, c)
    return send(db, f, render.friday(c.name, r, r.get("launches")), "friday", current={})


# ---------- inbound ----------
def _decide(db: Session, j: Job, decision: str, edited: str | None = None) -> str:
    from ..routers.jobs import _diff
    if j.state != "pending":
        return f"That one's already {j.state}."
    if decision == "reject":
        j.state = "rejected"
        db.commit()
        return "Dropped."
    if edited is not None and edited.strip() and edited.strip() != (j.output or {}).get("text"):
        j.approval_diff = _diff(j.output, {**j.output, "text": edited.strip()})
        j.output = {**j.output, "text": edited.strip()}
        j.state = "edited"
    else:
        j.state = "approved"
    if j.type in ("launch_task", "site_change"):
        j.state, j.platform_ref, j.executed_at = "executed", f"task-{j.id.hex[:8]}", datetime.now(timezone.utc)
        db.commit()
        return "Done." if j.type == "launch_task" else "Added to your site variant."
    db.commit()
    # publish at its slot, same as the app
    from ..queue import publish_q
    delay = (j.scheduled_for - datetime.now(timezone.utc)).total_seconds() if j.scheduled_for else 0
    if delay > 0:
        publish_q.enqueue_in(timedelta(seconds=delay), "workers.tasks.execute_job", str(j.id))
        when = j.scheduled_for.strftime("%a %-I%p").lower()
        return f"{'Edited and scheduled' if j.state == 'edited' else 'Scheduled'} for {when}."
    publish_q.enqueue("workers.tasks.execute_job", str(j.id))
    return "Sending now." if j.state == "approved" else "Edited, sending now."


def _batch_jobs(db: Session, st: SmsState, nums: list[int] | None) -> list[Job]:
    items = st.batch or []
    if nums:
        items = [i for i in items if i["n"] in nums]
    return [j for j in (db.get(Job, uuid.UUID(i["job_id"])) for i in items if i.get("job_id")) if j]


def handle_inbound(db: Session, payload: dict) -> list[str]:
    """Returns the replies sent (for tests and the webhook's TwiML)."""
    msg = get_messaging().parse_inbound(payload)
    phone = msg.from_phone
    f = db.scalars(select(Founder).where(Founder.phone == phone)).first()
    text = (msg.body or "").strip()
    low = text.lower().strip(" .!")
    out: list[str] = []

    def reply(body: str, kind: str = "ack", current: dict | None = None):
        if f:
            send(db, f, body, kind, current=current)
        else:
            get_messaging().send(to=phone, body=body)
        out.append(body)

    if not f:
        _log(db, None, "in", phone, text, kind="unknown", provider_ref=msg.provider_ref)
        reply("This number isn't linked to an account. Add your phone in settings to start.")
        return out

    st = _state(db, f)
    kind_in = "voice" if msg.media else ("command" if low in YES | NO | DONE | LATER or low.split()[:1] in (["yes"], ["no"], ["build"], ["change:"]) else "text")
    _log(db, f, "in", phone, text, kind=kind_in, media=msg.media, provider_ref=msg.provider_ref)

    # verification
    if st.pending_verify:
        if low == st.pending_verify:
            f.phone_verified_at = datetime.now(timezone.utc)
            st.pending_verify = None
            db.commit()
            reply(render.welcome(f.name, f"{settings.public_base_url}/setup/{f.company_id}"), "setup")
        else:
            reply("That code didn't match. Reply with the 6 digits from the first text.")
        return out

    # voice memo -> interview
    if msg.media:
        audio = [m for m in msg.media if (m.get("content_type") or "").startswith("audio")]
        if audio:
            tr = get_transcription()
            transcript = "\n".join(tr.transcribe(media_url=m["url"], content_type=m["content_type"]) for m in audio)
            if len(transcript) < 200:
                reply("Got the memo but it was short — try 5+ minutes of specifics: what shipped, what a customer said, a number.")
                return out
            from ..voice.engine import DraftPlan, run_voice_engine
            res = run_voice_engine(db, DraftPlan(company_id=f.company_id, founder_id=f.id, transcript=transcript, platforms=["linkedin", "x"]))
            first = None
            if res["created"]:
                j0 = db.get(Job, uuid.UUID(res["created"][0]))
                first = j0.scheduled_for.strftime("%a %-I%p").lower() if j0 and j0.scheduled_for else None
            reply(render.memo_ack(res["claims"], len(res["created"]), first), "memo_ack")
            return out

    # commands
    if low in ("help", "?"):
        reply(render.HELP); return out
    if low in ("pause", "stop"):
        st.paused = True; db.commit(); reply("Paused. Nothing will be sent or posted until you text resume.", "ack"); return out
    if low in ("resume", "start"):
        st.paused = False; db.commit(); reply("Resumed."); return out
    if low == "brief":
        send_brief(db, f); out.append("(brief)"); return out
    if low == "why":
        reply(render.why()); return out
    if low == "plan":
        from ..judgment.sequencer import commit_week, plan_week
        c = db.get(Company, f.company_id)
        p = commit_week(db, c, plan_week(db, c))
        w = (p.scorecard or {}).get("weekly") or {}
        reply(render.plan({"week_start": str(p.week_start), "focus": w.get("focus"), "decisions": w.get("decisions")})); return out
    if low.startswith("change:") or low.startswith("change "):
        from ..judgment.sequencer import override
        from ..models import Plan
        c = db.get(Company, f.company_id)
        p = db.scalars(select(Plan).where(Plan.company_id == c.id).order_by(Plan.week_start.desc())).first()
        changes = {}
        m = re.search(r"(\d+)\s*posts?", low)
        if m: changes["posts_per_platform"] = max(0, min(12, int(m.group(1))))
        m = re.search(r"(\d+)\s*repl", low)
        if m: changes["replies_per_platform"] = max(0, min(10, int(m.group(1))))
        if "no repl" in low: changes["replies_per_platform"] = 0
        if not changes or not p or "weekly" not in (p.scorecard or {}):
            reply("Tell me what to change, like 'change: 3 posts, no replies'."); return out
        override(db, p, changes, text, by=f"sms:{f.name}")
        reply("Changed for this week: " + ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in changes.items()) + "."); return out
    if m := re.fullmatch(r"build\s*([123])", low):
        ids = (st.current or {}).get("tool_ids") or []
        k = int(m.group(1)) - 1
        if k < len(ids):
            from ..tools.factory import decide as tool_decide
            t = db.get(Tool, uuid.UUID(ids[k]))
            t = tool_decide(db, t, True)
            reply(f"Building '{t.name}'. Live at {settings.public_base_url}/t/{t.company_id}/{t.slug} — two posts about it are in your queue.")
        else:
            reply("No tool ideas waiting. Text 'plan' and I'll propose some when search is in phase.")
        return out

    cur = st.current or {}
    nums = [int(x) for x in re.findall(r"\b(\d{1,2})\b", low)]
    head = low.split()[0] if low else ""

    # "3" alone -> show item 3
    if re.fullmatch(r"\d{1,2}", low) and st.batch:
        js = _batch_jobs(db, st, [int(low)])
        if js:
            send_item(db, f, js[0], int(low)); out.append("(item)"); return out
        reply(f"No item {low} on today's list."); return out

    # batch decisions: "yes 1 3", "no 2", or "all" / "yes all" (never a bare "yes": that shows the next item)
    if (head in ("yes", "no", "skip") and nums) or low in ("all", "yes all", "yes to all", "no all", "skip all"):
        js = _batch_jobs(db, st, nums or None)
        if not js:
            reply(render.nothing_pending()); return out
        approve = head in ("yes", "all")
        results = [_decide(db, j, "approve" if approve else "reject") for j in js]
        reply(f"{len(js)} {'approved' if approve else 'dropped'}. " + "; ".join(sorted(set(results))))
        done_ids = {str(j.id) for j in js}
        st.batch = [i for i in (st.batch or []) if i.get("job_id") not in done_ids]
        st.current = {}
        db.commit(); return out

    # single-item context
    if cur.get("kind") == "job":
        j = db.get(Job, uuid.UUID(cur["job_id"]))
        if not j:
            reply(render.nothing_pending()); return out
        if low in YES or low in DONE:
            reply(_decide(db, j, "approve"))
        elif low in NO:
            reply(_decide(db, j, "reject"))
        elif low in LATER:
            reply("Ok, holding it. It stays in your list.")
        elif len(text) >= 8:
            reply(_decide(db, j, "approve", edited=text))   # free text = the fix
        else:
            reply(render.clarify(["yes", "no", "or text the fix"]))
        st.current = {}; db.commit(); return out
    if cur.get("kind") == "joint":
        rel = db.get(Relationship, uuid.UUID(cur["relationship_id"]))
        from ..relationships.joint import decide as joint_decide
        c = db.get(Company, f.company_id)
        if low in YES:
            rel = joint_decide(db, rel, c, True)
            reply("Proposed. I'll tell you when they accept." if rel.state != "active" else "Both in — the joint launch calendar is in your list.")
        elif low in NO:
            joint_decide(db, rel, c, False); reply("Declined.")
        else:
            reply(render.clarify(["yes", "no"])); return out
        st.current = {}; db.commit(); return out
    if cur.get("kind") == "tools" and low in NO | {"skip"}:
        st.current = {}; db.commit(); reply("Skipped."); return out
    if cur.get("kind") == "meeting":
        m = db.get(Meeting, uuid.UUID(cur["meeting_id"]))
        if not m or m.state != "awaiting_founder":
            reply(render.nothing_pending()); st.current = {}; db.commit(); return out
        if low in YES:
            from ..meetings.engine import confirm
            m = confirm(db, m)
            reply(render.meeting_confirmed(m, f.timezone))
        elif low in NO:
            from ..meetings.engine import decline_and_reschedule
            m = decline_and_reschedule(db, m)
            reply("Declined that time." + (" New times sent." if m.state == "sent" else " Ran out of good options — I've marked it declined; text me if you want to try again."))
        else:
            reply(render.clarify(["yes to confirm", "no to try other times"])); return out
        st.current = {}; db.commit(); return out

    # nothing in context: a bare yes/no shows the next undecided item rather than guessing
    if low in YES | NO | DONE:
        remaining = [i for i in (st.batch or []) if (j := db.get(Job, uuid.UUID(i["job_id"]))) and j.state == "pending"]
        if remaining:
            send_item(db, f, db.get(Job, uuid.UUID(remaining[0]["job_id"])), remaining[0]["n"]); out.append("(item)")
        else:
            items = pending_items(db, f, 1)
            if items:
                send_item(db, f, db.get(Job, uuid.UUID(items[0]["job_id"])), 1); out.append("(item)")
            else:
                reply(render.nothing_pending())
        return out
    reply(render.clarify(["Send a voice memo about this week", "text 'brief' for today's list", "or 'help'"]))
    return out
