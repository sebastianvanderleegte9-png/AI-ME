"""Component 16: the client-facing metrics dashboard at /dashboard/{token}. Same setup-session-token
auth as /account, no new writes — it only reads what rollup()/write_outcome()/friday_close() and
Component 15's outreach/meetings already produce, shaped for display in the site's navy palette."""
import os
os.environ.setdefault("APP_ENV", "test")

import random
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal, migrate
from app.intake import pipeline
from app.intake.crawl import CrawlResult
from app.main import app

H = {"x-api-key": "dev-key"}


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


def _setup_company(client, email):
    r = client.post("/start", data={"email": email})
    token = r.headers["location"].split("/setup/")[1]
    client.post(f"/setup/{token}/1", data={"company_name": "Dash Test Co", "website": "dashtest.example",
                                           "one_line": "an ops copilot", "founder_name": "Noah Vance"})
    me = next(x for x in client.get("/setup-sessions", headers=H).json() if x["token"] == token)
    return token, me["company_id"]


def test_dashboard_with_no_history_renders_empty_states(client):
    email = f"noah+{random.randint(0, 99999)}@dashtest.example"
    token, cid = _setup_company(client, email)
    r = client.get(f"/dashboard/{token}")
    assert r.status_code == 200
    assert "Dash Test Co" in r.text
    assert "Not enough weeks yet" in r.text
    assert "No signups classified" in r.text
    assert "0" in r.text   # outreach/meeting stat tiles default to zero, not missing


def test_dashboard_unknown_token_404s(client):
    assert client.get("/dashboard/does-not-exist").status_code == 404


def test_dashboard_shows_trend_sources_score_and_outreach_stats(client):
    email = f"noah+{random.randint(0, 99999)}@dashtest.example"
    token, cid = _setup_company(client, email)

    r = client.post(f"/companies/{cid}/intake", headers=H, json={
        "site_url": "https://dashtest.example", "best_customers": [{"company": "A", "domain": "a.com"}]})
    assert r.status_code == 200
    client.patch(f"/companies/{cid}/icp", headers=H, json={"personas": [{"title": "COO"}], "firmographics": {"industry": ["software"]}})
    client.post(f"/companies/{cid}/scorecard", headers=H)

    with SessionLocal() as db:
        from sqlalchemy import select

        from app.models import Founder, Meeting, Metric, Outcome, Plan, SignupSource
        company_id = uuid.UUID(cid)

        # a plan with a scorecard, so the growth score tile has something to show
        plan = db.query(Plan).filter_by(company_id=company_id).order_by(Plan.created_at.desc()).first()
        plan.scorecard = {**(plan.scorecard or {}), "_overall": 7.4}
        db.add(plan)

        # two weeks of Outcome history for the trend line
        today = date.today()
        this_monday = today - timedelta(days=today.weekday())
        for i, val in enumerate([1200, 2100]):
            wk = this_monday - timedelta(weeks=(1 - i))
            db.add(Outcome(company_id=company_id, plan_id=plan.id, week_start=wk,
                            targets={}, actuals={"impressions_icp": val, "signups": i + 1},
                            delta={}, approval_rate=0.9, edit_rate=0.1))

        # current-week metric so rollup() has something for the trailing point + KPI tiles
        db.add(Metric(company_id=company_id, name="impressions_icp", value=3400, date=today, source="test"))
        db.add(Metric(company_id=company_id, name="signups", value=5, date=today, source="test"))

        # signup sources, three of the four fixed categorical slots
        for chan in ("linkedin", "linkedin", "x", "search"):
            db.add(SignupSource(company_id=company_id, answer_text=chan, classified_channel=chan, classified_by="test"))

        # a founder + one confirmed meeting so the outreach/meetings stat row is non-zero
        founder_id = db.execute(select(Founder.id).where(Founder.company_id == company_id)).scalar_one()
        db.add(Meeting(company_id=company_id, founder_id=founder_id, prospect_email="dana@prospect.example",
                       subject="Quick chat", state="confirmed", booking_token=f"tok-{uuid.uuid4().hex[:10]}",
                       confirmed_start=datetime.now(timezone.utc), confirmed_end=datetime.now(timezone.utc) + timedelta(minutes=30)))
        db.commit()

    r = client.get(f"/dashboard/{token}")
    assert r.status_code == 200
    body = r.text
    # KPI/score values render via a data-count attribute (animated client-side), not as static text
    assert 'data-count="3400"' in body     # this week's impressions_icp, from the live rollup
    assert "2,100" in body                 # last complete week's Outcome, the trend's end label (static SVG text)
    assert 'data-count="7.4"' in body      # growth score
    assert "Linkedin" in body and "Search" in body
    assert "#4f8ef7" in body and "#1fae76" in body and "#c2870f" in body   # fixed categorical order held
    assert 'data-count="1"' in body        # meetings confirmed tile
