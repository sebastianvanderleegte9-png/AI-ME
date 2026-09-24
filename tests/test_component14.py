"""Component 14: the whole website flow. Email -> company -> customers -> fake OAuth for both
platforms (tokens encrypted at rest) -> phone code by text, verified by replying -> preferences ->
free diagnostic (intake + scorecard + attention map, company still 'onboarding') -> checkout ->
activation -> the first text -> account page. Then the billing edge: a failed invoice pauses the
company and holds approved jobs; a fresh payment resumes them."""
import os
os.environ.setdefault("APP_ENV", "test")

import random

import pytest
from fastapi.testclient import TestClient

from app.db import migrate
from app.intake import pipeline
from app.intake.crawl import CrawlResult
from app.interfaces.billing_oauth import cipher
from app.main import app
from app.settings import settings

H = {"x-api-key": "dev-key"}
PHONE = f"+1786555{random.randint(1000, 9999)}"


@pytest.fixture(scope="session", autouse=True)
def _migrated():
    migrate()


@pytest.fixture
def client():
    return TestClient(app, follow_redirects=False)


@pytest.fixture(autouse=True)
def _offline_crawl(monkeypatch):
    monkeypatch.setattr(pipeline, "crawl", lambda root, extra=None, max_pages=12: CrawlResult(
        root=root, pages=[{"url": root, "title": "T", "text": "AI phone agents for real-estate brokerages. " * 20}]))


def _follow(client, r):
    while r.status_code in (302, 303):
        r = client.get(r.headers["location"])
    return r


def test_full_signup_to_first_text(client):
    email = f"juraj+{random.randint(0, 99999)}@simplicity.example"
    r = client.post("/start", data={"email": email})
    assert r.status_code == 303 and r.headers["location"].startswith("/setup/")
    token = r.headers["location"].split("/setup/")[1]
    assert _follow(client, r).status_code == 200                       # resumes at step 1
    assert "Your company" in _follow(client, client.get(f"/setup/{token}")).text

    # 1 company
    r = client.post(f"/setup/{token}/1", data={"company_name": "Simplicity AI", "website": "simplicity.example", "one_line": "AI phone agents for brokerages", "founder_name": "Juraj Gago"})
    assert r.headers["location"].endswith("/2")
    sessions = client.get("/setup-sessions", headers=H).json()
    me = next(x for x in sessions if x["token"] == token)
    assert me["step"] == 2 and me["company_id"]
    cid = me["company_id"]
    assert client.get(f"/companies/{cid}", headers=H).json()["status"] == "onboarding"

    # 2 customers: empty is refused; one is enough
    assert client.post(f"/setup/{token}/2", data={}).status_code == 422
    r = client.post(f"/setup/{token}/2", data={"c0_company": "Douglas Elliman", "c0_domain": "elliman.com", "c0_person": "Ops lead", "c0_role": "COO", "c0_why": "agents were drowning in calls",
                                               "c1_company": "ONE Sotheby's", "c1_domain": "onesothebysrealty.com"})
    assert r.headers["location"].endswith("/3")

    # 3 connect both via fake OAuth; the callback must carry the state we issued
    for p in ("linkedin", "x"):
        r = client.get(f"/setup/{token}/oauth/{p}")
        assert r.status_code == 303 and "/setup/oauth/" in r.headers["location"]
        r = client.get(r.headers["location"])
        assert r.status_code == 303 and r.headers["location"].endswith("/3")
    assert client.get(f"/setup/oauth/x/callback?state={token}:x:bogus&code=x").status_code == 400
    page = client.get(f"/setup/{token}/3").text
    assert page.count("connected") == 2
    from app.db import SessionLocal
    from app.models import Founder, OAuthToken
    with SessionLocal() as db:
        f = db.query(Founder).filter_by(email=email).one()
        assert f.linkedin_handle == "fake_linkedin_user" and f.x_handle == "fake_x_user"
        toks = db.query(OAuthToken).filter_by(founder_id=f.id).all()
        assert {t.platform for t in toks} == {"linkedin", "x"}
        for t in toks:
            assert b"tok-" not in t.ciphertext                            # never plaintext
            assert b"tok-" in cipher(settings.token_encryption_key).decrypt(t.ciphertext)
        fid = str(f.id)
    assert client.post(f"/setup/{token}/3").headers["location"].endswith("/4")

    # 4 phone: bad format refused; code texted; not verified until the founder replies
    assert client.post(f"/setup/{token}/4", data={"phone": "305 555"}).status_code == 422
    r = client.post(f"/setup/{token}/4", data={"phone": PHONE})
    assert r.headers["location"].endswith("/4")
    page = client.get(f"/setup/{token}/4").text
    assert "Check your phone" in page
    code = page.split("<code>")[1].split("</code>")[0]
    assert len(code) == 6
    assert client.post(f"/setup/{token}/4/check").status_code == 409
    replies = client.post("/sms/simulate", json={"From": PHONE, "Body": code}, headers=H).json()["replies"]
    assert replies[0].startswith("Linked.")
    assert client.post(f"/setup/{token}/4/check").headers["location"].endswith("/5")

    # 5 preferences
    r = client.post(f"/setup/{token}/5", data={"schedule_mode": "approve_times", "brief_hour": "7", "tz": "America/New_York"})
    assert r.headers["location"].endswith("/6")
    with SessionLocal() as db:
        f = db.get(Founder, fid)
        assert f.schedule_mode == "approve_times" and f.timezone == "America/New_York"

    # 6 free diagnostic (runs inline in test env); company must still be gated
    page = client.get(f"/setup/{token}/6").text
    assert "Your growth scorecard" in page and "/ 10 today" in page and "First two weeks" in page
    assert client.get(f"/companies/{cid}", headers=H).json()["status"] == "onboarding"
    assert client.get(f"/companies/{cid}/scorecard", headers=H).status_code == 200
    assert client.get(f"/companies/{cid}/subscription", headers=H).status_code == 404

    # 7 checkout with the fake provider -> success redirect completes -> active -> first text
    assert client.post(f"/setup/{token}/7", data={"plan": "nope"}).status_code == 422
    r = client.post(f"/setup/{token}/7", data={"plan": "founder"})
    assert r.status_code == 303 and "/paid?session=cs_fake_" in r.headers["location"]
    r = client.get(r.headers["location"].replace("http://localhost:8000", ""))
    assert r.headers["location"].endswith("/8")
    sub = client.get(f"/companies/{cid}/subscription", headers=H).json()
    assert sub["status"] == "active" and sub["plan"] == "founder"
    assert client.get(f"/companies/{cid}", headers=H).json()["status"] == "active"
    page = client.get(f"/setup/{token}/8").text
    assert "You're live" in page and "growth score today" in page and "voice memo" in page
    log = client.get(f"/founders/{fid}/sms/thread", headers=H).json()["messages"]
    kinds = [m["kind"] for m in log if m["dir"] == "out"]
    assert kinds[-1] == "first" and "verify" in kinds
    me = next(x for x in client.get("/setup-sessions", headers=H).json() if x["token"] == token)
    assert me["step"] == 8 and me["completed_at"]

    # account page
    page = client.get(f"/account/{token}").text
    assert "active" in page and "@fake_x_user" in page and "approve_times" in page and "Manage billing" in page

    # ---- billing edge: failed invoice pauses; approved jobs are held; payment resumes ----
    from app.models import Job
    with SessionLocal() as db:
        j = Job(company_id=cid, founder_id=fid, type="post", channel="x", state="approved", input={}, output={"text": "held post"})
        db.add(j)
        db.commit()
        jid = str(j.id)
    r = client.post("/public/billing/webhook", json={"kind": "invoice.failed", "company_id": cid, "status": "past_due"})
    assert r.json()["status"] == "past_due"
    assert client.get(f"/companies/{cid}", headers=H).json()["status"] == "paused"
    import workers.tasks as t
    assert t.execute_job(jid) == "held"
    r = client.post("/public/billing/webhook", json={"kind": "subscription.updated", "company_id": cid, "status": "active", "period_end": 4102444800})
    assert r.json()["status"] == "active"
    assert client.get(f"/companies/{cid}", headers=H).json()["status"] == "active"
    assert t.execute_job(jid) == "executed"
    assert "2100-01-01" in client.get(f"/companies/{cid}/subscription", headers=H).json()["period_end"]
    r = client.post("/public/billing/webhook", json={"kind": "subscription.deleted", "company_id": cid})
    assert client.get(f"/companies/{cid}", headers=H).json()["status"] == "churned"


def test_unknown_token_and_resume(client):
    assert client.get("/setup/nope").status_code == 404
    assert client.get("/account/nope").status_code == 404
    email = f"resume+{random.randint(0, 99999)}@x.example"
    t1 = client.post("/start", data={"email": email}).headers["location"]
    t2 = client.post("/start", data={"email": email}).headers["location"]
    assert t1 == t2                                                      # same email resumes the same session
    assert client.post("/start", data={"email": "not-an-email"}).status_code == 422
    assert "free diagnostic" in client.get("/start").text
