"""Component 2: scorecard produces five scored channels with fixes, a 90-day sequence,
targets, a plan row, and renders to HTML. Rules are deterministic over the fakes."""
import os
os.environ.setdefault("APP_ENV", "test")

import pytest
from fastapi.testclient import TestClient

from app.db import migrate
from app.intake import pipeline
from app.intake.crawl import CrawlResult
from app.judgment.rules import CHANNELS, FIXES, score_all
from app.judgment.signals import FounderSignals, Signals
from app.judgment.scorecard import sequence
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


def test_every_channel_has_a_fix_for_every_weakest():
    s = Signals(company_name="x", stage="seed")  # empty signals -> every channel at its floor
    for c in score_all(s):
        assert 0 <= c.score <= 10
        assert c.fix and c.fix_id != "review", (c.channel, c.weakest)


def test_scores_move_with_signals():
    weak = Signals(company_name="x", stage="seed", founders=[FounderSignals("f", "F", has_linkedin=True)])
    strong = Signals(company_name="x", stage="seed", founders=[FounderSignals(
        "f", "F", has_linkedin=True, has_x=True, linkedin_impressions_30d=300_000, linkedin_posts_30d=25)])
    w = {c.channel: c.score for c in score_all(weak)}
    s = {c.channel: c.score for c in score_all(strong)}
    assert s["founder_distribution"] > w["founder_distribution"] + 4


def test_sequence_puts_attribution_first_when_missing():
    s = Signals(company_name="x", stage="seed")
    seq = sequence(score_all(s))
    assert seq[0]["channel"] == "onboarding"
    assert {x["channel"] for x in seq} == {fn.__name__ for fn in CHANNELS}


def test_scorecard_end_to_end(client):
    co = client.post("/companies", json={"name": "Acme", "stage": "seed"}, headers=H).json()
    client.post(f"/companies/{co['id']}/founders", json={"name": "Jane", "linkedin_handle": "jane"}, headers=H)
    client.post(f"/companies/{co['id']}/intake", json={"site_url": "https://acme.example",
                "best_customers": [{"company": "A", "domain": "a.com"}]}, headers=H)
    r = client.post(f"/companies/{co['id']}/scorecard", headers=H)
    assert r.status_code == 200, r.text
    out = r.json()
    assert set(out["scorecard"]) >= {"founder_distribution", "icp_attention", "search", "launches", "onboarding", "_narrative", "_overall"}
    assert len(out["sequence"]) == 5
    assert out["targets"]["impressions_icp_weekly_12w"] >= 3 * out["targets"]["impressions_icp_weekly"] * 0.99
    assert out["scorecard"]["_narrative"]["headline"]
    html = client.get(f"/companies/{co['id']}/scorecard.html", headers=H)
    assert html.status_code == 200 and "Growth diagnostic" in html.text and "Fix:" in html.text
    # regenerating the same week updates, not duplicates
    r2 = client.post(f"/companies/{co['id']}/scorecard", headers=H).json()
    assert r2["plan_id"] == out["plan_id"]
