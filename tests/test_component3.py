"""Component 3: transcript -> drafts across formats and platforms, each voice-checked,
landing as pending jobs in the founder's feed; approve schedules publish at the slot;
banned phrases and slop patterns are caught; visuals render only when they carry data."""
import os
os.environ.setdefault("APP_ENV", "test")

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.db import migrate
from app.intake import pipeline
from app.intake.crawl import CrawlResult
from app.main import app
from app.voice.check import check
from app.voice.formats import FORMATS, formats_for
from app.voice.visuals import visual_for_job

H = {"x-api-key": "dev-key"}

TRANSCRIPT = """
So this week we shipped the Elli assistant to the Florida agents. I think most brokerages are wrong about AI;
they buy a chatbot and call it done. What actually happened is agents used it for CMA prep first, not client chat.
One agent told me she saved four hours on a listing packet. We measured it: 1,300 agents onboarded in six weeks.
We got the onboarding wrong the first time. We made them watch a 40 minute video and half never finished it.
We changed it to a two minute walkthrough inside the product and completion went to 80 percent.
Here is how we run a rollout now: first we pick ten agents who complain the loudest. Then we ship to them only.
Then we fix what they hit. Then we open it to everyone. I believe every enterprise AI rollout should start with the loudest ten.
The mistake was thinking compliance review would take two weeks. It took nine. Cost us a quarter.
Our head of product said something I keep repeating: nobody wants an assistant, they want the packet done.
""" * 2


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


def _founder(client):
    co = client.post("/companies", json={"name": "Acme", "stage": "seed"}, headers=H).json()
    f = client.post(f"/companies/{co['id']}/founders", json={"name": "Jane", "linkedin_handle": "jane", "x_handle": "jane"}, headers=H).json()
    client.post(f"/companies/{co['id']}/intake", json={"site_url": "https://acme.example",
                "best_customers": [{"company": "A", "domain": "a.com"}]}, headers=H)
    return co, f


def test_formats_cover_claim_types():
    assert set(FORMATS) == {"contrarian_take", "customer_story", "build_log", "teardown", "number_with_lesson",
                            "before_after", "framework", "question", "prediction", "mistake", "list", "quote_with_take"}
    assert "number_with_lesson" in formats_for({"number"})
    assert "customer_story" in formats_for({"story", "customer"})
    assert "customer_story" not in formats_for({"story"})


def test_check_catches_banned_and_slop():
    bad = check("Let's delve into this game-changer. It's not just a tool, it's a movement. Thoughts?",
                banned=["delve", "game-changer"], samples=[])
    assert not bad.passed and set(bad.banned_hits) == {"delve", "game-changer"}
    assert "its_not_x_its_y" in bad.pattern_hits and "generic_cta" in bad.pattern_hits
    ok = check("we shipped the assistant to 1,300 agents in six weeks. the packet is what they wanted.",
               banned=["delve"], samples=[])
    assert ok.passed and ok.score >= 0.62


def test_interview_to_feed_to_scheduled_publish(client):
    co, f = _founder(client)
    week = datetime.now(timezone.utc) + timedelta(days=1)
    r = client.post(f"/founders/{f['id']}/interview", json={"transcript": TRANSCRIPT, "platforms": ["linkedin", "x"],
                                                          "posts_per_platform": 4, "week_start": week.isoformat()}, headers=H)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["claims"] >= 8
    assert len(out["created"]) == 8, out
    assert out["avg_voice_match"] >= 0.62

    feed = client.get(f"/founders/{f['id']}/feed", headers=H).json()
    assert len(feed) == 8 and all(x["state"] == "pending" for x in feed)
    assert {x["channel"] for x in feed} == {"linkedin", "x"}
    assert len({x["format"] for x in feed}) >= 3           # spread across formats
    assert all(x["scheduled_for"] for x in feed)
    assert all(x["why"]["claim"] for x in feed)            # every draft traces to a claim

    # approve one in the future: state approved, not executed yet (publishes at slot)
    j = feed[0]
    d = client.post(f"/jobs/{j['id']}/decision", json={"decision": "approve"}, headers=H).json()
    assert d["state"] == "approved" and d["platform_ref"] is None

    # edit one: diff captured
    j2 = feed[1]
    d2 = client.post(f"/jobs/{j2['id']}/decision", json={"decision": "approve",
                     "edited_output": {"text": j2["text"] + "\n\n(edited)", "media": []}}, headers=H).json()
    assert d2["state"] == "edited"

    # reject one
    client.post(f"/jobs/{feed[2]['id']}/decision", json={"decision": "reject"}, headers=H)

    st = client.get(f"/founders/{f['id']}/voice/stats", headers=H).json()
    assert st["overall"]["decided"] == 3 and abs(st["overall"]["approval_rate"] - 2 / 3) < 0.01
    assert abs(st["overall"]["edit_rate"] - 0.5) < 0.01


def test_rules_edit_bumps_version_and_filters(client):
    co, f = _founder(client)
    r = client.patch(f"/founders/{f['id']}/voice/rules", json={"casing": "lower", "banned_phrases_add": ["synergy"],
                                                              "formats_allowed": ["number_with_lesson", "list"]}, headers=H).json()
    assert r["version"] == 2 and "synergy" in r["rules"]["banned_phrases"] and r["rules"]["casing"] == "lower"
    out = client.post(f"/founders/{f['id']}/interview", json={"transcript": TRANSCRIPT, "platforms": ["x"], "posts_per_platform": 3}, headers=H).json()
    feed = client.get(f"/founders/{f['id']}/feed", headers=H).json()
    assert {x["format"] for x in feed} <= {"number_with_lesson", "list"}


def test_visual_only_when_it_carries_data():
    brand = {"accent": "#ff0000"}
    none = visual_for_job({"format": "contrarian_take", "claim": {"text": "x"}}, {"text": "x"}, brand, "linkedin", "Jane")
    assert none is None
    html = visual_for_job({"format": "number_with_lesson", "claim": {"text": "agents onboarded", "number": "1,300", "evidence": "six weeks"}},
                          {"text": "x"}, brand, "linkedin", "Jane")
    assert html and "1,300" in html and "#ff0000" in html
