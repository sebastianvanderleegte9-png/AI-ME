"""Component 5: daily pull stores per-job metrics and impressions_icp (versioned method);
weekly rollup + outcome row; Friday report renders; signup-source classified and counted."""
import os
os.environ.setdefault("APP_ENV", "test")

from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.db import migrate
from app.intake import pipeline
from app.intake.crawl import CrawlResult
from app.main import app
from app.metrics.pull import METHOD, icp_share, ICP_PRIOR
from app.metrics.signup import classify
from workers.tasks import execute_job

H = {"x-api-key": "dev-key"}
TRANSCRIPT = ("We measured it: 1,300 agents onboarded in six weeks. I think most brokerages are wrong about AI. "
              "One agent told me she saved four hours on a listing packet. The mistake was thinking compliance would take two weeks. ") * 4


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


def _company_with_posts(client):
    co = client.post("/companies", json={"name": "Acme", "stage": "seed"}, headers=H).json()
    f = client.post(f"/companies/{co['id']}/founders", json={"name": "Jane", "linkedin_handle": "jane", "x_handle": "jane"}, headers=H).json()
    client.post(f"/companies/{co['id']}/intake", json={"site_url": "https://acme.example",
                "best_customers": [{"company": "A", "domain": "a.com", "role": "COO"}]}, headers=H)
    client.patch(f"/companies/{co['id']}/icp", json={"personas": [{"title": "COO"}], "firmographics": {"industry": ["real estate"]}}, headers=H)
    client.post(f"/companies/{co['id']}/scorecard", headers=H)
    client.post(f"/companies/{co['id']}/attention-map", headers=H)
    out = client.post(f"/founders/{f['id']}/interview", json={"transcript": TRANSCRIPT, "platforms": ["linkedin", "x"], "posts_per_platform": 3}, headers=H).json()
    for jid in out["created"]:
        client.post(f"/jobs/{jid}/decision", json={"decision": "approve"}, headers=H)
        execute_job(jid)
    return co, f, out["created"]


def test_signup_classifier():
    assert classify("saw it on LinkedIn")[0] == "linkedin"
    assert classify("a tweet from Cody")[0] == "x"
    assert classify("googled ai for brokerages")[0] == "search"
    assert classify("Product Hunt")[0] == "launch"
    assert classify("my colleague at Elliman")[0] == "referral"
    assert classify("")[0] == "other"


def test_icp_share_prior_and_observed(client):
    co, f, _ = _company_with_posts(client)
    from app.db import SessionLocal
    import uuid
    with SessionLocal() as db:
        share, how = icp_share(db, uuid.UUID(co["id"]), "linkedin", ["a", "b"])
        assert (share, how) == (ICP_PRIOR, "prior")
        m = client.get(f"/companies/{co['id']}/attention-map", params={"platform": "linkedin", "limit": 6}, headers=H).json()["accounts"]
        handles = [a["handle"] for a in m][:5] + ["nobody1", "nobody2"]
        share, how = icp_share(db, uuid.UUID(co["id"]), "linkedin", handles)
        assert how == "observed" and 0 <= share < 1


def test_pull_rollup_outcome_report(client):
    co, f, jobs = _company_with_posts(client)
    r = client.post(f"/companies/{co['id']}/metrics/pull", headers=H).json()
    assert r["jobs_measured"] == len(jobs) and r["impressions_icp"] > 0 and r["method"] == METHOD
    ms = client.get("/metrics", params={"company_id": co["id"], "name": "impressions_icp"}, headers=H).json()
    assert len(ms) == len(jobs) and all(m["source"] == METHOD for m in ms)
    # pulling twice on the same day updates, not duplicates
    client.post(f"/companies/{co['id']}/metrics/pull", headers=H)
    assert len(client.get("/metrics", params={"company_id": co["id"], "name": "impressions_icp"}, headers=H).json()) == len(jobs)

    # signups arrive via the public receiver (no api key)
    for a in ("LinkedIn post", "a friend", "google"):
        assert client.post(f"/public/{co['id']}/signup-source", json={"answer": a}).status_code == 201
    assert "data-me-signup" in client.get(f"/public/{co['id']}/signup-widget.js").text

    rep = client.get(f"/companies/{co['id']}/report", headers=H).json()
    assert rep["this"]["impressions_icp"] == r["impressions_icp"]
    assert rep["approval_rate"] == 1.0 and rep["decided"] == len(jobs)
    assert len(rep["top_posts"]) == 3 and rep["top_posts"][0]["impressions_icp"] >= rep["top_posts"][-1]["impressions_icp"]
    assert rep["signup_sources"] == {"linkedin": 1, "referral": 1, "search": 1}

    o = client.post(f"/companies/{co['id']}/report/close-week", headers=H).json()
    assert o["actuals"]["impressions_icp"] == r["impressions_icp"] and "impressions_icp_weekly" in o["targets"]
    assert o["delta"]["approval_gate"] is True
    # idempotent per week
    assert client.post(f"/companies/{co['id']}/report/close-week", headers=H).json()["outcome_id"] == o["outcome_id"]

    html = client.get(f"/companies/{co['id']}/report.html", headers=H)
    assert html.status_code == 200 and "impressions inside your ICP" in html.text and f"{r['impressions_icp']:,}" in html.text


def test_close_week_needs_plan(client):
    co = client.post("/companies", json={"name": "NoPlan"}, headers=H).json()
    assert client.post(f"/companies/{co['id']}/report/close-week", headers=H).status_code == 422
