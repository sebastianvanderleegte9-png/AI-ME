"""Component 6: the sequencer re-plans from the outcome row with named, explained rules;
its settings steer the voice engine; overrides are applied and logged as labeled examples."""
import os
os.environ.setdefault("APP_ENV", "test")

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal, migrate
from app.intake import pipeline
from app.intake.crawl import CrawlResult
from app.judgment.sequencer import plan_week
from app.main import app
from app.models import Company, Outcome, Plan

H = {"x-api-key": "dev-key"}
T = ("We measured it: 1,300 agents onboarded. I think most brokerages are wrong about AI. One agent said she saved four hours. "
     "The mistake was assuming compliance took two weeks. Here is how we run a rollout now: first ten, then everyone. ") * 4


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
    this_monday = date.today() - timedelta(days=date.today().weekday())
    client.post(f"/companies/{co['id']}/scorecard", params={"week_start": str(this_monday - timedelta(days=14))}, headers=H)
    return co, f, this_monday


def _seed_outcomes(co_id, monday, prev_icp, prev2_icp, approval, edit):
    import uuid
    with SessionLocal() as db:
        plan = db.query(Plan).filter_by(company_id=uuid.UUID(co_id)).first()
        for ws, icp in ((monday - timedelta(days=14), prev2_icp), (monday - timedelta(days=7), prev_icp)):
            db.add(Outcome(company_id=uuid.UUID(co_id), plan_id=plan.id, week_start=ws, targets=plan.targets,
                           actuals={"impressions_icp": icp, "approval_rate": approval, "edit_rate": edit},
                           approval_rate=approval, edit_rate=edit))
        db.commit()


def test_first_week_uses_standing_sequence(client):
    co, f, monday = _setup(client)
    r = client.post(f"/companies/{co['id']}/week", params={"week_start": str(monday)}, headers=H)
    assert r.status_code == 200, r.text
    out = r.json()
    rules = {d["rule"] for d in out["decisions"]}
    assert "R1.phase" in rules and out["focus"]
    assert out["settings"]["posts_per_platform"] == 5
    assert all(d["reason"] for d in out["decisions"])
    # idempotent
    assert client.post(f"/companies/{co['id']}/week", params={"week_start": str(monday)}, headers=H).json()["plan_id"] == out["plan_id"]


def test_low_approval_cuts_volume_and_plateau_adds_replies(client):
    co, f, monday = _setup(client)
    _seed_outcomes(co["id"], monday, prev_icp=1000, prev2_icp=980, approval=0.5, edit=0.3)
    out = client.post(f"/companies/{co['id']}/week", params={"week_start": str(monday)}, headers=H).json()
    rules = {d["rule"] for d in out["decisions"]}
    assert "R3.approval_gate" in rules and out["settings"]["posts_per_platform"] == 3
    assert "R4.edit_rate" in rules and out["settings"]["retrain_voice"] is True
    assert "R5.plateau" not in rules  # plateau rule requires approval >= 0.7


def test_plateau_with_good_approval_shifts_mix(client):
    co, f, monday = _setup(client)
    _seed_outcomes(co["id"], monday, prev_icp=1000, prev2_icp=980, approval=0.9, edit=0.05)
    out = client.post(f"/companies/{co['id']}/week", params={"week_start": str(monday)}, headers=H).json()
    rules = {d["rule"] for d in out["decisions"]}
    assert "R5.plateau" in rules and out["settings"]["replies_per_platform"] == 8
    assert "R3.approval_gate" not in rules


def test_momentum_holds_mix(client):
    co, f, monday = _setup(client)
    _seed_outcomes(co["id"], monday, prev_icp=3000, prev2_icp=1000, approval=0.9, edit=0.05)
    out = client.post(f"/companies/{co['id']}/week", params={"week_start": str(monday)}, headers=H).json()
    assert "R6.momentum" in {d["rule"] for d in out["decisions"]}
    assert out["settings"]["posts_per_platform"] == 5


def test_settings_steer_voice_engine_and_override_is_logged(client):
    co, f, monday = _setup(client)
    client.post(f"/companies/{co['id']}/week", params={"week_start": str(monday)}, headers=H)
    o = client.post(f"/companies/{co['id']}/week/override", json={
        "changes": {"posts_per_platform": 2, "format_weights": {"number_with_lesson": 5.0}},
        "reason": "founder travelling; keep it light and numeric", "by": "sebastian"}, headers=H).json()
    assert o["generated_by"] == "human" and o["settings"]["posts_per_platform"] == 2
    assert o["overrides"][0]["before"]["posts_per_platform"] == 5 and o["overrides"][0]["by"] == "sebastian"
    # the interview now defaults to the week's settings
    out = client.post(f"/founders/{f['id']}/interview", json={"transcript": T, "platforms": ["linkedin"]}, headers=H).json()
    assert len(out["created"]) + len(out["dropped"]) == 2
    feed = client.get(f"/founders/{f['id']}/feed", headers=H).json()
    assert any(j["format"] == "number_with_lesson" for j in feed)
