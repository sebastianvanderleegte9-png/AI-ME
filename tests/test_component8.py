"""Component 8: a launch expands its playbook into dated jobs; content tasks are voice-drafted
posts in the feed; checklist tasks complete on tap; the sequencer proposes a launch when
in phase; close writes results; the report shows the launch."""
import os
os.environ.setdefault("APP_ENV", "test")

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.db import migrate
from app.intake import pipeline
from app.intake.crawl import CrawlResult
from app.launch.playbooks import PH_V1, PLAYBOOKS
from app.main import app

H = {"x-api-key": "dev-key"}
BRIEF = {"what": "Elli AI now drafts the full listing packet in one click", "why_now": "agents spend 4 hours per packet and brokerages are buying chatbots that don't do the work",
         "hook": "the packet, not the chat", "proof": ["1,300 agents onboarded in six weeks", "4 hours saved per packet"],
         "number": "4 hours", "customer": "ONE Sotheby's", "target_signups": 150}


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


def _setup(client):
    co = client.post("/companies", json={"name": "Acme", "stage": "seed"}, headers=H).json()
    f = client.post(f"/companies/{co['id']}/founders", json={"name": "Jane", "linkedin_handle": "jane", "x_handle": "jane"}, headers=H).json()
    client.post(f"/companies/{co['id']}/intake", json={"site_url": "https://acme.example", "best_customers": [{"company": "A", "domain": "a.com"}]}, headers=H)
    return co, f


def test_playbooks_are_well_formed():
    for kind, (pid, tasks) in PLAYBOOKS.items():
        assert tasks and all({"day", "kind", "title", "detail"} <= set(t) for t in tasks)
        assert all(t.get("channel") and t.get("format") for t in tasks if t["kind"] == "post")
        assert any(t["day"] == 0 for t in tasks) and any(t["day"] > 0 for t in tasks)
    assert client is not None and len(PH_V1) >= 20


def test_launch_expands_into_feed_and_closes(client):
    co, f = _setup(client)
    ld = date.today() + timedelta(days=45)
    r = client.post(f"/companies/{co['id']}/launches", json={"type": "product_hunt", "name": "Packet launch",
                                                            "launch_date": str(ld), "brief": BRIEF}, headers=H)
    assert r.status_code == 201, r.text
    L = r.json()
    assert L["status"] == "active" and L["playbook"] == "ph-v1"
    ex = L["expanded"]
    assert ex["created"] == len(PH_V1) and ex["posts"] > 5 and ex["tasks"] > 5

    cal = client.get(f"/launches/{L['id']}", headers=H).json()["calendar"]
    assert cal[0]["day"] == -42 and cal[-1]["day"] == 7
    assert cal[0]["date"] == str(ld - timedelta(days=42))
    posts = [x for x in cal if x["type"] == "post"]
    assert all(x["state"] == "pending" and x["text"] for x in posts)
    # launch-day posts exist for both channels
    assert {x["channel"] for x in cal if x["day"] == 0 and x["type"] == "post"} == {"linkedin", "x"}

    # they show in the founder's feed, tagged with the launch
    feed = client.get(f"/founders/{f['id']}/feed", headers=H).json()
    tagged = [j for j in feed if j["launch"]]
    assert len(tagged) == len(PH_V1) and tagged[0]["launch"]["title"]

    # a checklist task completes on tap, with no publish
    task = next(j for j in feed if j["launch"] and j["format"] == "task")
    d = client.post(f"/jobs/{task['id']}/decision", json={"decision": "approve"}, headers=H).json()
    assert d["state"] == "executed" and d["platform_ref"].startswith("task-")

    # expand is idempotent
    assert client.post(f"/launches/{L['id']}/expand", headers=H).json()["created"] == 0

    # close writes results and the report shows the launch
    closed = client.post(f"/launches/{L['id']}/close", headers=H).json()
    assert closed["status"] == "closed" and closed["results"]["tasks_done"] == 1 and closed["results"]["target_signups"] == 150
    client.post(f"/companies/{co['id']}/scorecard", headers=H)
    rep = client.get(f"/companies/{co['id']}/report", headers=H).json()
    assert any(x["name"] == "Packet launch" for x in rep["launches"])


def test_sequencer_proposes_launch_when_in_phase(client):
    co, f = _setup(client)
    monday = date.today() - timedelta(days=date.today().weekday())
    # standing sequence with launches in weeks 1-2 so R8 fires now
    client.post(f"/companies/{co['id']}/scorecard", params={"week_start": str(monday)}, headers=H)
    from app.db import SessionLocal
    from app.models import Plan
    import uuid
    with SessionLocal() as db:
        p = db.query(Plan).filter_by(company_id=uuid.UUID(co["id"]), week_start=monday).first()
        p.sequence = [{"channel": "launches", "start_week": 1, "end_week": 2, "fix_id": "launch_calendar", "fix": "x", "score_now": 2, "target_score_12w": 6}]
        db.commit()
    w = client.post(f"/companies/{co['id']}/week", params={"week_start": str(monday)}, headers=H).json()
    rules = {d["rule"] for d in w["decisions"]}
    assert "R8.launch_propose" in rules and w["settings"]["proposed_launch"]["type"] == "feature_drop"
    # create it; next re-plan sees it as active
    client.post(f"/companies/{co['id']}/launches", json={"type": "feature_drop", "name": "Drop", "brief": BRIEF}, headers=H)
    w2 = client.post(f"/companies/{co['id']}/week", params={"week_start": str(monday)}, headers=H).json()
    assert "R8.launch_active" in {d["rule"] for d in w2["decisions"]}


def test_launch_date_validation(client):
    co, f = _setup(client)
    r = client.post(f"/companies/{co['id']}/launches", json={"type": "feature_drop", "name": "Too soon", "launch_date": str(date.today())}, headers=H)
    assert r.status_code == 422
    assert client.post(f"/companies/{co['id']}/launches", json={"type": "nope", "name": "Bad type"}, headers=H).status_code == 422
