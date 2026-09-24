"""Component 15: personalized outreach email over Outlook, and the meeting-booking loop it
feeds into. Connect Outlook -> propose emails to real prospects (same approval feed as
everything else) -> approve by text -> sent through the founder's own address -> the prospect
'replies interested' -> the bot proposes times from the founder's calendar -> the prospect
books a slot on a public page -> the founder approves or denies by text -> denied reschedules
automatically, approved creates the calendar event -> the morning brief maps the day."""
import os
os.environ.setdefault("APP_ENV", "test")

import random

import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal, migrate
from app.intake import pipeline
from app.intake.crawl import CrawlResult
from app.main import app

H = {"x-api-key": "dev-key"}
PHONE = f"+1786556{random.randint(1000, 9999)}"


@pytest.fixture(scope="session", autouse=True)
def _migrated():
    migrate()


@pytest.fixture
def client():
    return TestClient(app, follow_redirects=False)


@pytest.fixture(autouse=True)
def _offline_crawl(monkeypatch):
    monkeypatch.setattr(pipeline, "crawl", lambda root, extra=None, max_pages=12: CrawlResult(
        root=root, pages=[{"url": root, "title": "T", "text": "AI ops copilot for revenue teams. " * 20}]))


def _follow(client, r):
    while r.status_code in (302, 303):
        r = client.get(r.headers["location"])
    return r


def _setup_company(client, email):
    r = client.post("/start", data={"email": email})
    token = r.headers["location"].split("/setup/")[1]
    client.post(f"/setup/{token}/1", data={"company_name": "Aime Test Co", "website": "aimetest.example",
                                           "one_line": "an ops copilot", "founder_name": "Noah Vance"})
    me = next(x for x in client.get("/setup-sessions", headers=H).json() if x["token"] == token)
    return token, me["company_id"]


def _connect(client, token, platform):
    r = client.get(f"/setup/{token}/oauth/{platform}")
    r = client.get(r.headers["location"])
    assert r.status_code == 303


def test_email_outreach_needs_voice_profile_then_needs_outlook_then_works(client):
    email = f"noah+{random.randint(0, 99999)}@aimetest.example"
    token, cid = _setup_company(client, email)
    with SessionLocal() as db:
        from app.models import Founder
        fid = str(db.query(Founder).filter_by(email=email).one().id)

    # no voice profile yet -> refused
    r = client.post(f"/companies/{cid}/relationships/email-outreach", headers=H,
                    json={"founder_id": fid, "prospects": [{"name": "Dana Lee", "email": "dana@prospect.example", "company": "Prospect Co", "why": "50-person sales team, manual CRM entry"}]})
    assert r.status_code == 422

    # intake builds the voice profile
    r = client.post(f"/companies/{cid}/intake", headers=H, json={"site_url": "https://aimetest.example", "best_customers": [{"company": "A", "domain": "a.com"}]})
    assert r.status_code == 200

    # voice profile exists now, but Outlook isn't connected -> the job is created and approvable,
    # but executing it fails cleanly rather than silently doing nothing
    r = client.post(f"/companies/{cid}/relationships/email-outreach", headers=H,
                    json={"founder_id": fid, "prospects": [{"name": "Dana Lee", "email": "dana@prospect.example", "company": "Prospect Co", "why": "50-person sales team, manual CRM entry"}]})
    assert r.status_code == 201
    j1 = r.json()[0]
    assert j1["state"] == "pending" and j1["voice_match"] is not None
    r = client.post(f"/jobs/{j1['job_id']}/decision", headers=H, json={"decision": "approve"})
    assert r.status_code == 200
    import workers.tasks as t
    assert t.execute_job(j1["job_id"]) == "failed"
    with SessionLocal() as db:
        from app.models import Job
        row = db.get(Job, j1["job_id"])
        assert row.state == "failed" and "Outlook isn't connected" in row.error

    # connect Outlook
    _connect(client, token, "outlook")
    with SessionLocal() as db:
        import uuid as _uuid
        from app.models import OAuthToken
        tok = db.query(OAuthToken).filter_by(founder_id=_uuid.UUID(fid), platform="outlook").one()
        assert tok.handle == "fake.founder@outlook.example"
        assert b"tok-outlook-" not in tok.ciphertext   # encrypted at rest

    # a second prospect, approved, now actually sends
    r = client.post(f"/companies/{cid}/relationships/email-outreach", headers=H,
                    json={"founder_id": fid, "prospects": [{"name": "Priya Shah", "email": "priya@otherprospect.example", "company": "Other Co", "why": "growing outbound team, no personalization today"}]})
    j2 = r.json()[0]
    client.post(f"/jobs/{j2['job_id']}/decision", headers=H, json={"decision": "approve"})
    assert t.execute_job(j2["job_id"]) == "executed"
    from app.interfaces import get_email
    fake_email = get_email()
    assert any(s["to"] == "priya@otherprospect.example" for s in fake_email.sent)


def test_full_meeting_loop_propose_book_approve_and_decline(client):
    email = f"noah+{random.randint(0, 99999)}@aimetest.example"
    token, cid = _setup_company(client, email)
    with SessionLocal() as db:
        from app.models import Founder
        f = db.query(Founder).filter_by(email=email).one()
        fid = str(f.id)
    client.post(f"/companies/{cid}/intake", headers=H, json={"site_url": "https://aimetest.example", "best_customers": [{"company": "A", "domain": "a.com"}]})
    _connect(client, token, "outlook")
    r = client.post(f"/founders/{fid}/phone", headers=H, json={"phone": PHONE})
    code = r.json()["code"]
    client.post("/sms/simulate", json={"From": PHONE, "Body": code}, headers=H)

    r = client.post(f"/companies/{cid}/relationships/email-outreach", headers=H,
                    json={"founder_id": fid, "prospects": [{"name": "Dana Lee", "email": "dana@prospect.example", "company": "Prospect Co", "why": "manual CRM entry"}]})
    job_id = r.json()[0]["job_id"]
    client.post(f"/jobs/{job_id}/decision", headers=H, json={"decision": "approve"})
    import workers.tasks as t
    assert t.execute_job(job_id) == "executed"

    # prospect replies interested -> bot proposes 3 times over email
    r = client.post(f"/jobs/{job_id}/interested", headers=H, params={"note": "yes let's talk this week"})
    assert r.status_code == 200
    m = r.json()
    assert m["state"] == "sent" and len(m["proposed_slots"]) == 3
    booking_url = m["booking_url"]
    from app.interfaces import get_email
    assert any("dana@prospect.example" == s["to"] for s in get_email().sent)

    # public booking page shows the times, no auth
    page = client.get(booking_url.replace("http://localhost:8000", "")).text
    assert m["subject"] in page and "Noah Vance" in page

    # prospect picks the first slot -> founder gets a text with meeting context
    r = client.post(booking_url.replace("http://localhost:8000", "") + "/0")
    assert "Thanks" in r.text
    thread = client.get(f"/founders/{fid}/sms/thread", headers=H).json()
    last_out = [x for x in thread["messages"] if x["dir"] == "out"][-1]
    assert last_out["kind"] == "meeting" and "Dana" in last_out["body"]
    assert thread["state"]["current"]["kind"] == "meeting"

    # founder denies -> automatic reschedule: new slots, same meeting, still not confirmed
    replies = client.post("/sms/simulate", json={"From": PHONE, "Body": "no"}, headers=H).json()["replies"]
    assert "new times" in replies[0].lower() or "declined" in replies[0].lower()
    m2 = client.get(f"/meetings/{m['id']}", headers=H).json()
    assert m2["state"] == "sent" and m2["chosen_slot"] is None and len(m2["proposed_slots"]) == 3

    # pick again, this time approve
    r = client.post(m2["booking_url"].replace("http://localhost:8000", "") + "/0")
    replies = client.post("/sms/simulate", json={"From": PHONE, "Body": "yes"}, headers=H).json()["replies"]
    assert "Confirmed" in replies[0]
    m3 = client.get(f"/meetings/{m['id']}", headers=H).json()
    assert m3["state"] == "confirmed" and m3["confirmed_start"] and m3["calendar_event_ref"]

    from app.interfaces import get_calendar
    with SessionLocal() as db:
        from app.interfaces.tokens import access_token
        tok = access_token(db, f.id, "outlook")
    assert any(e.event_ref == m3["calendar_event_ref"] for e in get_calendar().events.get(tok, []))

    # morning brief maps the day: force the confirmed time to "now" so the assertion isn't
    # time-of-day dependent, then check the brief names it before the numbered list
    from datetime import datetime, timedelta, timezone
    with SessionLocal() as db:
        from app.models import Meeting
        mm = db.get(Meeting, m3["id"])
        mm.confirmed_start = datetime.now(timezone.utc) + timedelta(hours=1)
        mm.confirmed_end = mm.confirmed_start + timedelta(minutes=30)
        db.commit()
    r = client.post(f"/founders/{fid}/sms/brief", headers=H)
    sent = r.json()["sent"]
    assert "On your calendar:" in sent and "Dana" in sent
