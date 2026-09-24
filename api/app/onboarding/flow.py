"""The setup wizard (Component 14). Eight steps, each idempotent, each a call into things
that already exist. The session token in the URL is the only credential during setup.

  1 company   name, website, one line, founder name  -> company + founder rows
  2 customers three best customers                    -> stored; intake runs in step 6
  3 connect   LinkedIn / X OAuth                       -> oauth_token rows (encrypted), founder handles
  4 phone     number -> code by text -> reply verifies -> founder.phone_verified_at
  5 prefs     schedule mode, brief hour, timezone
  6 diagnostic (free) intake -> scorecard -> attention map, in the background; the summary is shown
  7 pay       Stripe Checkout; webhook activates
  8 done      first text goes out; company.status = active

Free diagnostic before paywall: a founder sees their score and 90-day plan before paying;
nothing posts until the subscription is active."""
from datetime import datetime, timedelta, timezone
import json
import secrets
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..interfaces import get_billing, get_oauth
from ..interfaces.billing_oauth import PLANS, cipher
from ..models import Company, Founder, OAuthToken, SetupSession, Subscription
from ..settings import settings

STEPS = {1: "company", 2: "customers", 3: "connect", 4: "phone", 5: "preferences", 6: "diagnostic", 7: "pay", 8: "done"}


def start(db: Session, email: str) -> SetupSession:
    s = db.scalars(select(SetupSession).where(SetupSession.email == email.lower(), SetupSession.completed_at.is_(None))
                   .order_by(SetupSession.created_at.desc())).first()
    if s:
        return s
    s = SetupSession(token=secrets.token_urlsafe(24), email=email.lower())
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def by_token(db: Session, token: str) -> SetupSession | None:
    return db.scalars(select(SetupSession).where(SetupSession.token == token)).first()


def link(s: SetupSession) -> str:
    return f"{settings.public_base_url}/setup/{s.token}"


def _advance(db: Session, s: SetupSession, to: int, **data) -> SetupSession:
    s.data = {**(s.data or {}), **data}
    s.step = max(s.step, to)
    db.commit()
    db.refresh(s)
    return s


def step1_company(db: Session, s: SetupSession, *, company_name: str, website: str, one_line: str, founder_name: str) -> SetupSession:
    if s.company_id:
        c = db.get(Company, s.company_id)
        c.name, c.domain = company_name, website.replace("https://", "").replace("http://", "").strip("/")
        f = db.get(Founder, s.founder_id)
        f.name = founder_name
    else:
        c = Company(name=company_name, domain=website.replace("https://", "").replace("http://", "").strip("/"),
                    stage="seed", status="onboarding", product_summary=json.dumps({"one_liner": one_line}))
        db.add(c)
        db.flush()
        f = Founder(company_id=c.id, name=founder_name, email=s.email)
        db.add(f)
        db.flush()
        s.company_id, s.founder_id = c.id, f.id
        from ..learning.experiment import assign
        assign(db, c)
    return _advance(db, s, 2, company_name=company_name, website=website, one_line=one_line, founder_name=founder_name)


def step2_customers(db: Session, s: SetupSession, customers: list[dict]) -> SetupSession:
    clean = [{"company": c.get("company", "").strip(), "person": c.get("person", "").strip(), "role": c.get("role", "").strip(),
              "why_they_bought": c.get("why_they_bought", "").strip(), "domain": c.get("domain", "").strip() or None}
             for c in customers if c.get("company", "").strip()]
    if len(clean) < 1:
        raise ValueError("name at least one customer")
    return _advance(db, s, 3, customers=clean)


def oauth_start(db: Session, s: SetupSession, platform: str) -> str:
    state = f"{s.token}:{platform}:{secrets.token_hex(6)}"
    s.data = {**(s.data or {}), f"oauth_state_{platform}": state}
    db.commit()
    return get_oauth().authorize_url(platform=platform, state=state, redirect_uri=f"{settings.public_base_url}/setup/oauth/{platform}/callback")


def oauth_finish(db: Session, s: SetupSession, platform: str, state: str, code: str) -> SetupSession:
    if (s.data or {}).get(f"oauth_state_{platform}") != state:
        raise ValueError("oauth state mismatch")
    res = get_oauth().exchange(platform=platform, code=code, redirect_uri=f"{settings.public_base_url}/setup/oauth/{platform}/callback")
    f = db.get(Founder, s.founder_id)
    payload = json.dumps({"access_token": res.access_token, "refresh_token": res.refresh_token}).encode()
    tok = db.get(OAuthToken, (f.id, platform))
    if not tok:
        tok = OAuthToken(founder_id=f.id, platform=platform, ciphertext=b"")
        db.add(tok)
    tok.handle, tok.scopes = res.handle, res.scopes
    tok.ciphertext = cipher(settings.token_encryption_key).encrypt(payload)
    tok.expires_at = datetime.now(timezone.utc) + timedelta(seconds=res.expires_in) if res.expires_in else None
    if platform == "linkedin":
        f.linkedin_handle = res.handle
    elif platform == "outlook":
        f.email = f.email or res.handle   # Outlook connect also gives us a confirmed work email
    else:
        f.x_handle = res.handle
    connected = sorted(set((s.data or {}).get("connected", [])) | {platform})
    return _advance(db, s, 4 if connected else 3, connected=connected)


def step3_skip_connect(db: Session, s: SetupSession) -> SetupSession:
    """Allowed: a founder can connect later from the account page. Nothing can post until they do."""
    return _advance(db, s, 4, connected=(s.data or {}).get("connected", []))


def step4_phone(db: Session, s: SetupSession, phone: str) -> str:
    from ..sms.engine import start_verify
    f = db.get(Founder, s.founder_id)
    code = start_verify(db, f, phone)
    _advance(db, s, 4, phone=phone)
    return code


def phone_is_verified(db: Session, s: SetupSession) -> bool:
    f = db.get(Founder, s.founder_id)
    ok = bool(f and f.phone_verified_at)
    if ok and s.step < 5:
        _advance(db, s, 5)
    return ok


def step5_preferences(db: Session, s: SetupSession, *, schedule_mode: str, brief_hour: int, tz: str) -> SetupSession:
    f = db.get(Founder, s.founder_id)
    f.schedule_mode = schedule_mode if schedule_mode in ("managed", "approve_times") else "managed"
    f.timezone = tz or "America/New_York"
    from ..models import SmsState
    st = db.get(SmsState, f.id)
    if st:
        st.brief_hour = max(5, min(12, int(brief_hour)))
    return _advance(db, s, 6, schedule_mode=f.schedule_mode, brief_hour=brief_hour, tz=f.timezone)


def step6_diagnostic(db: Session, s: SetupSession) -> dict:
    """Runs intake, scorecard and attention map now (synchronously here; the worker task does the same
    in the background for the web route). Returns the summary the page shows."""
    from ..attention.map import build_map
    from ..intake.pipeline import IntakeInput, run_intake
    from ..judgment.scorecard import build_scorecard
    c, f = db.get(Company, s.company_id), db.get(Founder, s.founder_id)
    d = s.data or {}
    if not d.get("intake_done"):
        try:
            run_intake(db, IntakeInput(company_id=c.id, site_url=d["website"], docs_urls=[], best_customers=d["customers"],
                                       founder_handles=[{"founder_id": str(f.id), "linkedin_handle": f.linkedin_handle, "x_handle": f.x_handle}],
                                       site_text=d.get("site_text") or f"{d.get('company_name', '')}. {d.get('one_line', '')} " * 30))
        except ValueError:
            run_intake(db, IntakeInput(company_id=c.id, site_url=d["website"], docs_urls=[], best_customers=d["customers"],
                                       founder_handles=[{"founder_id": str(f.id), "linkedin_handle": f.linkedin_handle, "x_handle": f.x_handle}],
                                       site_text=f"{d.get('company_name', '')}. {d.get('one_line', '')} " * 30))
        c.status = "onboarding"   # intake flips to active; hold until paid
        db.commit()
    plan = build_scorecard(db, c)
    try:
        build_map(db, c)
    except ValueError:
        pass
    sc = plan.scorecard
    summary = {"overall": sc.get("_overall"), "headline": (sc.get("_narrative") or {}).get("headline"),
               "channels": {k: v["score"] for k, v in sc.items() if isinstance(v, dict) and "score" in v},
               "first_two_weeks": (sc.get("_narrative") or {}).get("first_two_weeks"),
               "pdf": f"{settings.public_base_url}/companies/{c.id}/scorecard.pdf"}
    _advance(db, s, 7, intake_done=True, diagnostic=summary)
    return summary


def step7_checkout(db: Session, s: SetupSession, plan: str) -> str:
    if plan not in PLANS:
        raise ValueError("unknown plan")
    sub = db.get(Subscription, s.company_id)
    if not sub:
        sub = Subscription(company_id=s.company_id, plan=plan, status="incomplete")
        db.add(sub)
    sub.plan = plan
    db.commit()
    cs = get_billing().create_checkout(company_id=str(s.company_id), email=s.email, plan=plan,
                                       success_url=f"{settings.public_base_url}/setup/{s.token}/paid",
                                       cancel_url=f"{settings.public_base_url}/setup/{s.token}")
    _advance(db, s, 7, checkout_ref=cs.session_ref, plan=plan)
    return cs.url


def apply_billing_event(db: Session, ev) -> Subscription | None:
    """Webhook: subscription state drives company.status. A lapsed card pauses posting; data stays."""
    if not ev or not ev.company_id:
        return None
    cid = uuid.UUID(ev.company_id)
    sub = db.get(Subscription, cid)
    c = db.get(Company, cid)
    if not c:
        return None
    if not sub:
        sub = Subscription(company_id=cid, plan=ev.plan or "founder")
        db.add(sub)
    sub.customer_ref = ev.customer_ref or sub.customer_ref
    sub.subscription_ref = ev.subscription_ref or sub.subscription_ref
    if ev.plan:
        sub.plan = ev.plan
    if ev.period_end:
        sub.current_period_end = datetime.fromtimestamp(ev.period_end, tz=timezone.utc)
    status = {"checkout.completed": "active", "subscription.deleted": "canceled", "invoice.failed": "past_due"}.get(ev.kind, ev.status or sub.status)
    sub.status = status if status in ("incomplete", "trialing", "active", "past_due", "canceled", "paused") else sub.status
    c.status = "active" if sub.status in ("active", "trialing") else "paused" if sub.status in ("past_due", "paused") else "churned" if sub.status == "canceled" else c.status
    if sub.status in ("active", "trialing"):
        s = db.scalars(select(SetupSession).where(SetupSession.company_id == cid, SetupSession.completed_at.is_(None))).first()
        if s:
            s.step, s.completed_at = 8, datetime.now(timezone.utc)
    db.commit()
    return sub


def is_active(db: Session, company_id) -> bool:
    sub = db.get(Subscription, company_id)
    return bool(sub and sub.status in ("active", "trialing"))


def first_text(db: Session, s: SetupSession) -> str | None:
    """After activation: the diagnostic summary and the memo ask, as the first real text."""
    from ..sms import engine, render
    f = db.get(Founder, s.founder_id)
    if not (f and f.phone_verified_at):
        return None
    d = (s.data or {}).get("diagnostic") or {}
    body = (f"You're live. Your growth score today: {d.get('overall')}/10. {d.get('headline') or ''}\n"
            f"First: {(d.get('first_two_weeks') or ['install the signup field'])[0]}\n"
            f"Send me a 10-minute voice memo about what happened this week whenever you're ready, and I'll start drafting.")
    engine.send(db, f, body, "first", current={})
    return body
