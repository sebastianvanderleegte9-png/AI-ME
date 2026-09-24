"""Component 4: attention map builds scored, clustered accounts from the ICP; daily
targets produce voice-checked reply jobs in the feed; replied-to accounts cool down."""
import os
os.environ.setdefault("APP_ENV", "test")

import pytest
from fastapi.testclient import TestClient

from app.db import migrate
from app.intake import pipeline
from app.intake.crawl import CrawlResult
from app.main import app

H = {"x-api-key": "dev-key"}


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
    client.post(f"/companies/{co['id']}/intake", json={"site_url": "https://acme.example",
                "best_customers": [{"company": "Big Brokerage", "domain": "big.com", "role": "COO"},
                                   {"company": "Mid Realty", "domain": "mid.com", "role": "VP Ops"}]}, headers=H)
    # give the ICP personas so seeds and role matching have something to work with
    client.patch(f"/companies/{co['id']}/icp", json={
        "personas": [{"title": "VP Sales", "where_they_pay_attention": "LinkedIn"}, {"title": "Founder"}],
        "firmographics": {"industry": ["real estate"], "size_band": "200-2000"}}, headers=H)
    return co, f


def test_map_builds_scored_clusters(client):
    co, f = _setup(client)
    r = client.post(f"/companies/{co['id']}/attention-map", headers=H)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["found"] >= 20 and out["stored"] == out["found"]
    assert set(out["clusters"]) & {"buyer", "peer", "influencer", "community"}
    m = client.get(f"/companies/{co['id']}/attention-map", headers=H).json()
    accs = m["accounts"]
    assert accs and all(0 <= a["icp_match"] <= 1 for a in accs)
    assert accs == sorted(accs, key=lambda a: -a["icp_match"])
    assert {a["platform"] for a in accs} == {"linkedin", "x"}
    # rebuild is idempotent (updates, not duplicates)
    out2 = client.post(f"/companies/{co['id']}/attention-map", headers=H).json()
    assert client.get(f"/companies/{co['id']}/attention-map", params={"limit": 1000}, headers=H).json()["accounts"].__len__() == out2["stored"]


def test_daily_targets_land_in_feed_and_cool_down(client):
    co, f = _setup(client)
    client.post(f"/companies/{co['id']}/attention-map", headers=H)
    r = client.post(f"/founders/{f['id']}/targets", json={"per_platform": 3}, headers=H)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["by_platform"] == {"linkedin": 3, "x": 3}
    feed = client.get(f"/founders/{f['id']}/feed", headers=H).json()
    replies = [j for j in feed if j["format"] == "reply"]
    assert len(replies) == 6
    assert all(j["voice_match"] >= 0.62 for j in replies)
    # each reply targets a real thread and carries the why
    j = client.get(f"/jobs/{replies[0]['id']}", headers=H).json()
    assert j["input"]["reply_to_ref"] and j["input"]["post_text"] and j["input"]["cluster"]
    # approve + execute now (scheduled_for is this morning, in the past) -> account cools down
    client.post(f"/jobs/{replies[0]['id']}/decision", json={"decision": "approve"}, headers=H)
    from workers.tasks import execute_job
    assert execute_job(replies[0]["id"]) == "executed"
    m = client.get(f"/companies/{co['id']}/attention-map", params={"limit": 1000}, headers=H).json()
    acc = next(a for a in m["accounts"] if a["id"] == j["input"]["account_id"])
    assert acc["interaction"]["last_replied_at"] and acc["interaction"]["replies"] == 1
    # next day's targets skip that account
    out2 = client.post(f"/founders/{f['id']}/targets", json={"per_platform": 3}, headers=H).json()
    handles2 = {client.get(f"/jobs/{i}", headers=H).json()["input"]["account_id"] for i in out2["created"]}
    assert j["input"]["account_id"] not in handles2


def test_map_requires_icp(client):
    co = client.post("/companies", json={"name": "NoICP"}, headers=H).json()
    assert client.post(f"/companies/{co['id']}/attention-map", headers=H).status_code == 422
