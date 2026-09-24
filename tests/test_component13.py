"""Component 13: a whole founder relationship over SMS — link and verify a phone; voice memo
becomes drafts; morning brief numbers them; 'yes 1 3' / 'no 2' / a number / free-text edits
decide jobs the same way taps do; joint proposals and tool builds answer to yes/build; plan
and change work; Friday sends the number; pause suppresses; unknown numbers are refused."""
import os
os.environ.setdefault("APP_ENV", "test")

from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from app.db import migrate
from app.intake import pipeline
from app.intake.crawl import CrawlResult
from app.interfaces import get_messaging
from app.main import app

H = {"x-api-key": "dev-key"}
import random as _r
PHONE = f"+1305555{_r.randint(1000, 9999)}"
PHONE2 = f"+1305556{_r.randint(1000, 9999)}"
MEMO = ("This week we shipped the listing packet to the Florida agents. One agent told me she saved four hours per packet. "
        "We measured it: 1,300 agents onboarded in six weeks. We got the onboarding wrong the first time; half never finished the video. "
        "I believe most brokerages are wrong about AI. Here is how we run a rollout now: first the ten loudest agents, then everyone. "
        "The mistake was assuming compliance would take two weeks. It took nine. ") * 2


@pytest.fixture(scope="session", autouse=True)
def _migrated():
    migrate()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def _offline_crawl(monkeypatch):
    monkeypatch.setattr(pipeline, "crawl", lambda root, extra=None, max_pages=12: CrawlResult(
        root=root, pages=[{"url": root, "title": "T", "text": "An AI assistant for brokerages. " * 20}]))


def sms(client, body, phone=PHONE, media_text=None):
    payload = {"From": phone, "Body": body}
    if media_text is not None:
        payload.update({"NumMedia": "1", "MediaUrl0": f"https://media.example/m.ogg?text={quote(media_text)}", "MediaContentType0": "audio/ogg"})
    return client.post("/sms/simulate", json=payload, headers=H).json()["replies"]


def _setup(client, phone=PHONE, name="Jane"):
    co = client.post("/companies", json={"name": "Acme", "domain": "acme.example", "stage": "seed"}, headers=H).json()
    f = client.post(f"/companies/{co['id']}/founders", json={"name": name, "linkedin_handle": name.lower(), "x_handle": name.lower()}, headers=H).json()
    client.post(f"/companies/{co['id']}/intake", json={"site_url": "https://acme.example", "best_customers": [{"company": "A", "domain": "a.com"}]}, headers=H)
    client.post(f"/companies/{co['id']}/scorecard", headers=H)
    r = client.post(f"/founders/{f['id']}/phone", json={"phone": phone}, headers=H).json()
    assert r["sent"] and len(r["code"]) == 6
    return co, f, r["code"]


def test_unknown_number_is_refused(client):
    assert "isn't linked" in sms(client, "hello", phone="+19999999999")[0]


def test_verify_memo_brief_decide(client):
    co, f, code = _setup(client)
    assert "didn't match" in sms(client, "000000")[0]
    w = sms(client, code)[0]
    assert w.startswith("Linked.") and "/setup/" in w

    # a short memo is bounced; a real one becomes drafts
    assert "short" in sms(client, "", media_text="too short")[0]
    ack = sms(client, "", media_text=MEMO)[0]
    assert ack.startswith("Got it") and "drafts coming" in ack
    feed = client.get(f"/founders/{f['id']}/feed", headers=H).json()
    assert len(feed) >= 6 and all(j["state"] == "pending" for j in feed)

    # morning brief: numbered, with the memo line absent (we just sent one)
    b = client.post(f"/founders/{f['id']}/sms/brief", headers=H).json()["sent"]
    assert b.startswith("Morning, Jane.") and "1. Post" in b and "Reply: yes (all)" in b and "voice memo" not in b
    n_items = b.count("\n") - 2

    # "2" shows item 2; then free text edits it
    sent = get_messaging().sent
    sms(client, "2")
    shown = sent[-1]["body"]
    assert shown.startswith("#2 ·") and "yes / no / or text the fix" in shown
    r = sms(client, "we shipped the packet feature to 1,300 agents in six weeks. the number surprised us.")[0]
    assert r.startswith("Edited")
    thread = client.get(f"/founders/{f['id']}/sms/thread", headers=H).json()
    assert thread["state"]["current"] == {}

    # batch: yes 1 3, no 4
    r = sms(client, "yes 1 3")[0]
    assert r.startswith("2 approved")
    r = sms(client, "no 4")[0]
    assert r.startswith("1 dropped")
    states = {j["id"]: j["state"] for j in client.get(f"/founders/{f['id']}/feed", params={"state": "all"}, headers=H).json()}
    assert list(states.values()).count("approved") == 2 and list(states.values()).count("rejected") == 1 and list(states.values()).count("edited") == 1

    # a bare yes with nothing in context shows the next undecided item rather than guessing
    sms(client, "yes")
    assert sent[-1]["body"].startswith("#5 ·")
    r = sms(client, "no")[0]
    assert r == "Dropped."

    # commands
    assert "Impressions inside ICP" in sms(client, "why")[0]
    p = sms(client, "plan")[0]
    assert p.startswith("This week") and "Reply change" in p
    c = sms(client, "change: 3 posts, no replies")[0]
    assert "posts per platform 3" in c and "replies per platform 0" in c
    wk = client.get(f"/companies/{co['id']}/week", headers=H).json()
    assert wk["settings"]["posts_per_platform"] == 3 and wk["overrides"][0]["by"] == "sms:Jane"
    assert sms(client, "help")[0].startswith("Commands")

    # friday
    fr = client.post(f"/founders/{f['id']}/sms/friday", headers=H).json()["sent"]
    assert "impressions inside your ICP" in fr and "Reply why" in fr

    # pause suppresses outbound, resume restores
    assert sms(client, "pause")[0].startswith("Paused")
    before = len(sent)
    client.post(f"/founders/{f['id']}/sms/brief", headers=H)
    assert len(sent) == before
    assert sms(client, "resume")[0] == "Resumed."


def test_tools_and_joint_over_sms(client):
    co, f, code = _setup(client, phone=PHONE2, name="Maya")
    sms(client, code, phone=PHONE2)
    from app.db import SessionLocal
    from app.models import Company
    import json, uuid
    with SessionLocal() as db:
        c = db.get(Company, uuid.UUID(co["id"]))
        c.product_summary = json.dumps({"one_liner": "x", "data_assets": ["rollout metrics"], "proof_points": ["p"], "competitors_mentioned": []})
        db.commit()
    client.post(f"/companies/{co['id']}/tools/propose", headers=H)
    t = client.post(f"/founders/{f['id']}/sms/tools", headers=H).json()["sent"]
    assert t.startswith("3 free tools") and "Reply build 1, 2 or 3" in t
    r = sms(client, "build 2", phone=PHONE2)[0]
    assert r.startswith("Building") and "/t/" in r
    tools = client.get(f"/companies/{co['id']}/tools", headers=H).json()
    assert sum(1 for x in tools if x["status"] == "published") == 1

    # joint launch: seed a partner and a proposal, then answer over SMS
    from sqlalchemy import text
    P = client.post("/companies", json={"name": "Partner", "stage": "seed"}, headers=H).json()
    client.post(f"/companies/{P['id']}/founders", json={"name": "Pat", "linkedin_handle": "pat"}, headers=H)
    client.post(f"/companies/{P['id']}/intake", json={"site_url": "https://p.example", "best_customers": [{"company": "B", "domain": "b.com"}]}, headers=H)
    with SessionLocal() as db:
        c = db.get(Company, uuid.UUID(P["id"]))
        c.product_summary = json.dumps({"one_liner": "mortgage automation", "proof_points": ["2,000 loans"], "competitors_mentioned": []})
        v = [0.0] * 1536; v[0] = 1.0
        db.execute(text("UPDATE icp SET embedding=:v WHERE company_id=:c"), {"v": str(v), "c": co["id"]})
        v = [0.0] * 1536; v[0], v[1] = 0.8, 0.6
        db.execute(text("UPDATE icp SET embedding=:v WHERE company_id=:c"), {"v": str(v), "c": P["id"]})
        db.commit()
    rel = client.post(f"/companies/{co['id']}/relationships/joint", json={"partner_company_id": P["id"]}, headers=H).json()
    j = client.post(f"/founders/{f['id']}/sms/joint/{rel['id']}", headers=H).json()["sent"]
    assert j.startswith("Joint launch idea: Partner") and "yes to propose" in j
    r = sms(client, "yes", phone=PHONE2)[0]
    assert r.startswith("Proposed")
    st = client.get(f"/companies/{co['id']}/relationships", headers=H).json()["relationships"][0]["state"]
    assert st == "accepted_by_us"
