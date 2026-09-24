"""Component 14: the public website flow. /start -> /setup/{token}/... -> Stripe -> webhook -> live.
Everything under /setup and /account is authenticated by the session token in the URL;
/public/billing/webhook by the provider signature."""
import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import require_api_key
from ..db import get_db
from ..interfaces import get_billing
from ..models import Founder, OAuthToken, Subscription
from ..onboarding import flow, pages, site
from ..settings import settings

router = APIRouter(tags=["onboarding"])
SYNC = settings.app_env in ("local", "test")   # run background steps inline where there may be no worker


def _sess(db: Session, token: str):
    s = flow.by_token(db, token)
    if not s:
        raise HTTPException(404, "setup link not found")
    return s


def _go(s, step: int | None = None) -> RedirectResponse:
    return RedirectResponse(f"/setup/{s.token}" + (f"/{step}" if step else ""), status_code=303)


def _enqueue(fn: str, *args):
    if SYNC:
        import workers.tasks as t
        return getattr(t, fn)(*args)
    from ..queue import generate_q
    generate_q.enqueue(f"workers.tasks.{fn}", *args)


# ---------- site ----------
@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def home():
    return site.page()


# ---------- landing ----------
@router.get("/start", response_class=HTMLResponse)
def landing():
    return pages.landing()


@router.post("/start")
def start(email: str = Form(...), db: Session = Depends(get_db)):
    if "@" not in email:
        return HTMLResponse(pages.landing("that doesn't look like an email"), status_code=422)
    s = flow.start(db, email)
    return _go(s)


# ---------- wizard ----------
@router.get("/setup/{token}", response_class=HTMLResponse)
def resume(token: str, db: Session = Depends(get_db)):
    s = _sess(db, token)
    return _go(s, s.step)


@router.get("/setup/{token}/paid")
def paid(token: str, session: str = "", fake: str = "", db: Session = Depends(get_db)):
    """Stripe's success_url. The webhook is the source of truth; this page just waits for it.
    With the fake provider there is no webhook, so the success redirect completes the purchase itself."""
    s = _sess(db, token)
    if fake and settings.billing_provider == "fake":
        _activate(db, s, {"kind": "checkout.completed", "company_id": str(s.company_id), "plan": (s.data or {}).get("plan", "founder"),
                          "customer_ref": "cus_fake", "subscription_ref": session or "sub_fake"})
    return _go(s, 8)


@router.get("/setup/{token}/{step}", response_class=HTMLResponse)
def show(token: str, step: int, db: Session = Depends(get_db)):
    s = _sess(db, token)
    step = min(step, s.step)
    if step == 1:
        return pages.step1(s)
    if step == 2:
        return pages.step2(s)
    if step == 3:
        return pages.step3(s)
    if step == 4:
        return pages.step4(s, sent=bool((s.data or {}).get("phone")), code_hint=(s.data or {}).get("code_hint") if SYNC else None)
    if step == 5:
        return pages.step5(s)
    if step == 6:
        d = s.data or {}
        if d.get("diagnostic"):
            return pages.step6(s, d["diagnostic"])
        if not d.get("diagnostic_queued"):
            s.data = {**d, "diagnostic_queued": True}
            db.commit()
            _enqueue("onboarding_diagnostic", s.token)
            db.refresh(s)
            if (s.data or {}).get("diagnostic"):
                return pages.step6(s, s.data["diagnostic"])
        return pages.step6_wait(s)
    if step == 7:
        if flow.is_active(db, s.company_id):
            return _go(s, 8)
        return pages.step7(s)
    if step == 8:
        if not flow.is_active(db, s.company_id):
            return pages.step7_pending(s)
        d = s.data or {}
        return pages.step8(s, d.get("first_text"))
    return _go(s, s.step)


@router.post("/setup/{token}/1")
def post1(token: str, company_name: str = Form(...), website: str = Form(...), one_line: str = Form(...), founder_name: str = Form(...),
          site_text: str = Form(""), db: Session = Depends(get_db)):
    s = _sess(db, token)
    if not website.startswith("http"):
        website = "https://" + website
    flow.step1_company(db, s, company_name=company_name.strip(), website=website.strip(), one_line=one_line.strip(), founder_name=founder_name.strip())
    if site_text.strip():
        s.data = {**s.data, "site_text": site_text.strip()}
        db.commit()
    return _go(s, 2)


@router.post("/setup/{token}/2")
async def post2(token: str, request: Request, db: Session = Depends(get_db)):
    s = _sess(db, token)
    form = dict(await request.form())
    customers = [{"company": form.get(f"c{i}_company", ""), "domain": form.get(f"c{i}_domain", ""), "person": form.get(f"c{i}_person", ""),
                  "role": form.get(f"c{i}_role", ""), "why_they_bought": form.get(f"c{i}_why", "")} for i in range(3)]
    try:
        flow.step2_customers(db, s, customers)
    except ValueError as ex:
        return HTMLResponse(pages.step2(s, str(ex)), status_code=422)
    return _go(s, 3)


@router.get("/setup/{token}/oauth/{platform}")
def oauth_start(token: str, platform: str, db: Session = Depends(get_db)):
    if platform not in ("linkedin", "x"):
        raise HTTPException(404)
    s = _sess(db, token)
    return RedirectResponse(flow.oauth_start(db, s, platform), status_code=303)


@router.get("/setup/oauth/{platform}/callback")
def oauth_callback(platform: str, state: str = "", code: str = "", error: str = "", db: Session = Depends(get_db)):
    token = state.split(":", 1)[0]
    s = _sess(db, token)
    if error:
        return _go(s, 3)
    try:
        flow.oauth_finish(db, s, platform, state, code)
    except ValueError as ex:
        raise HTTPException(400, str(ex))
    if s.completed_at:
        return RedirectResponse(f"/account/{s.token}", status_code=303)
    return _go(s, 3)


@router.post("/setup/{token}/3")
def post3(token: str, db: Session = Depends(get_db)):
    s = _sess(db, token)
    flow.step3_skip_connect(db, s)
    return _go(s, 4)


@router.post("/setup/{token}/4")
def post4(token: str, phone: str = Form(...), db: Session = Depends(get_db)):
    s = _sess(db, token)
    phone = phone.strip().replace(" ", "").replace("-", "")
    if not phone.startswith("+") or not phone[1:].isdigit():
        return HTMLResponse(pages.step4(s, error="use the international format, e.g. +13055551234"), status_code=422)
    code = flow.step4_phone(db, s, phone)
    if SYNC:
        s.data = {**s.data, "code_hint": code}
        db.commit()
    return _go(s, 4)


@router.post("/setup/{token}/4/check")
def post4_check(token: str, db: Session = Depends(get_db)):
    s = _sess(db, token)
    if flow.phone_is_verified(db, s):
        return _go(s, 5)
    return HTMLResponse(pages.step4(s, sent=True, code_hint=(s.data or {}).get("code_hint") if SYNC else None,
                                    error="not verified yet: reply to the text with the code, then tap again"), status_code=409)


@router.post("/setup/{token}/5")
def post5(token: str, schedule_mode: str = Form("managed"), brief_hour: int = Form(8), tz: str = Form("America/New_York"), db: Session = Depends(get_db)):
    s = _sess(db, token)
    flow.step5_preferences(db, s, schedule_mode=schedule_mode, brief_hour=brief_hour, tz=tz)
    return _go(s, 6)


@router.post("/setup/{token}/7")
def post7(token: str, plan: str = Form("founder"), db: Session = Depends(get_db)):
    s = _sess(db, token)
    try:
        url = flow.step7_checkout(db, s, plan)
    except ValueError as ex:
        return HTMLResponse(pages.step7(s, str(ex)), status_code=422)
    return RedirectResponse(url, status_code=303)


def _activate(db: Session, s, payload: dict):
    import json
    ev = get_billing().parse_webhook({}, json.dumps(payload).encode())
    flow.apply_billing_event(db, ev)
    db.refresh(s)
    if flow.is_active(db, s.company_id) and not (s.data or {}).get("first_text"):
        body = flow.first_text(db, s)
        s.data = {**(s.data or {}), "first_text": body}
        db.commit()


@router.post("/public/billing/webhook")
async def billing_webhook(request: Request, db: Session = Depends(get_db)):
    body = await request.body()
    ev = get_billing().parse_webhook(dict(request.headers), body)
    if ev is None:
        raise HTTPException(400, "bad signature or unhandled event")
    sub = flow.apply_billing_event(db, ev)
    if sub is None:
        return {"ok": True, "ignored": True}
    if sub.status in ("active", "trialing"):
        s = db.scalars(select(flow.SetupSession).where(flow.SetupSession.company_id == sub.company_id).order_by(flow.SetupSession.created_at.desc())).first()
        if s and not (s.data or {}).get("first_text"):
            body_text = flow.first_text(db, s)
            s.data = {**(s.data or {}), "first_text": body_text}
            db.commit()
    return {"ok": True, "company_id": str(sub.company_id), "status": sub.status}


# ---------- account ----------
@router.get("/account/{token}", response_class=HTMLResponse)
def account(token: str, db: Session = Depends(get_db)):
    s = _sess(db, token)
    sub = db.get(Subscription, s.company_id) if s.company_id else None
    f = db.get(Founder, s.founder_id)
    toks = db.scalars(select(OAuthToken).where(OAuthToken.founder_id == s.founder_id)).all() if s.founder_id else []
    portal = get_billing().portal_url(customer_ref=sub.customer_ref, return_url=f"{settings.public_base_url}/account/{s.token}") if sub and sub.customer_ref else None
    return pages.account(s, sub, f, toks, portal)


# ---------- admin ----------
@router.get("/companies/{company_id}/subscription", dependencies=[Depends(require_api_key)])
def subscription(company_id: uuid.UUID, db: Session = Depends(get_db)):
    sub = db.get(Subscription, company_id)
    if not sub:
        raise HTTPException(404, "no subscription")
    return {"company_id": str(company_id), "plan": sub.plan, "status": sub.status, "customer_ref": sub.customer_ref,
            "period_end": sub.current_period_end.isoformat() if sub.current_period_end else None}


@router.get("/setup-sessions", dependencies=[Depends(require_api_key)])
def sessions(db: Session = Depends(get_db)):
    rows = db.scalars(select(flow.SetupSession).order_by(flow.SetupSession.created_at.desc()).limit(100)).all()
    return [{"token": r.token, "email": r.email, "step": r.step, "step_name": flow.STEPS.get(r.step), "company_id": str(r.company_id) if r.company_id else None,
             "completed_at": r.completed_at.isoformat() if r.completed_at else None} for r in rows]
