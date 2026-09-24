"""Component 11: three tools proposed from product + ICP; specs validated (formulas restricted);
publish serves a working page and queues distribution posts; events count views/runs/leads and
leads land in signup_source; the sequencer proposes tools when none is live."""
import os
os.environ.setdefault("APP_ENV", "test")

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.db import migrate
from app.intake import pipeline
from app.intake.crawl import CrawlResult
from app.main import app
from app.tools.factory import validate_spec

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
    co = client.post("/companies", json={"name": "Acme", "domain": "acme.example", "stage": "seed"}, headers=H).json()
    f = client.post(f"/companies/{co['id']}/founders", json={"name": "Jane", "linkedin_handle": "jane", "x_handle": "jane"}, headers=H).json()
    client.post(f"/companies/{co['id']}/intake", json={"site_url": "https://acme.example", "best_customers": [{"company": "A", "domain": "a.com"}]}, headers=H)
    client.patch(f"/companies/{co['id']}/icp", json={"personas": [{"title": "COO"}], "firmographics": {"industry": ["brokerage"]}}, headers=H)
    return co, f


def test_validate_spec_restricts_logic():
    base = {"kind": "calculator", "inputs": [{"id": "a", "type": "number"}, {"id": "b", "type": "number"}], "result": {"headline": "{value}"}}
    assert validate_spec({**base, "logic": {"formula": "a * b / 2"}})[0]
    assert not validate_spec({**base, "logic": {"formula": "a * c"}})[0]              # unknown id
    assert not validate_spec({**base, "logic": {"formula": "fetch(`x`)"}})[0]         # disallowed chars
    assert not validate_spec({**base, "kind": "scorecard", "logic": {"rules": []}})[0]
    assert not validate_spec({**base, "kind": "generator", "logic": {}})[0]


def test_propose_publish_serve_events(client):
    co, f = _setup(client)
    ideas = client.post(f"/companies/{co['id']}/tools/propose", headers=H).json()
    assert len(ideas) == 3 and {i["kind"] for i in ideas} >= {"calculator", "scorecard", "generator"}
    assert all(i["status"] == "proposed" and i["rationale"] and i["spec"]["data_source"] for i in ideas)
    calc = next(i for i in ideas if i["kind"] == "calculator")
    # not served while proposed
    assert client.get(f"/t/{co['id']}/{calc['slug']}").status_code == 404
    # bad edit rejected, good edit accepted
    assert client.patch(f"/tools/{calc['id']}/spec", json={"spec": {"logic": {"formula": "people * evil()"}}}, headers=H).status_code == 422
    ok = client.patch(f"/tools/{calc['id']}/spec", json={"spec": {"logic": {"formula": "people * tasks_week * 4 * (minutes - 10) / 60", "unit": "hours / month"}}}, headers=H).json()
    assert ok["status"] == "draft"
    # publish -> served, with the evaluator and the spec inline; distribution posts queued
    pub = client.post(f"/tools/{calc['id']}/decide", json={"approve": True}, headers=H).json()
    assert pub["status"] == "published" and len(pub["distribution_jobs"]) == 2
    page = client.get(f"/t/{co['id']}/{calc['slug']}")
    assert page.status_code == 200 and "function ev(" in page.text and "people * tasks_week" in page.text and "sendBeacon" in page.text
    feed = client.get(f"/founders/{f['id']}/feed", headers=H).json()
    assert sum(1 for j in feed if j["state"] == "pending" and j["channel"] in ("linkedin", "x")) >= 2
    # events
    for k, p in (("view", {}), ("view", {}), ("run", {"inputs": {"people": 10}}), ("lead", {"email": "a@b.co"})):
        assert client.post(f"/public/tools/{calc['id']}/event", json={"kind": k, "payload": p}).status_code == 201
    st = next(t for t in client.get(f"/companies/{co['id']}/tools", headers=H).json() if t["id"] == calc["id"])["stats"]
    assert st == {"views": 2, "runs": 1, "leads": 1, "run_rate": 0.5, "lead_rate": 1.0}
    # the lead is attributed to the tool in the weekly report's signup sources
    client.post(f"/companies/{co['id']}/scorecard", headers=H)
    rep = client.get(f"/companies/{co['id']}/report", headers=H).json()
    assert rep["signup_sources"].get(f"tool:{calc['slug']}") == 1
    # re-propose skips existing slugs
    assert client.post(f"/companies/{co['id']}/tools/propose", headers=H).json() == []


def test_sequencer_proposes_tools_when_none_live(client):
    co, f = _setup(client)
    monday = date.today() - timedelta(days=date.today().weekday())
    client.post(f"/companies/{co['id']}/scorecard", params={"week_start": str(monday)}, headers=H)
    from app.db import SessionLocal
    from app.models import Plan
    import uuid
    with SessionLocal() as db:
        p = db.query(Plan).filter_by(company_id=uuid.UUID(co["id"]), week_start=monday).first()
        p.sequence = [{"channel": "search", "start_week": 1, "end_week": 4, "fix_id": "page_factory", "fix": "x", "score_now": 2, "target_score_12w": 6}]
        db.commit()
    w = client.post(f"/companies/{co['id']}/week", params={"week_start": str(monday)}, headers=H).json()
    assert "R9.tool" in {d["rule"] for d in w["decisions"]} and w["settings"]["propose_tools"] is True
    client.post(f"/companies/{co['id']}/tools/propose", headers=H)
    w2 = client.post(f"/companies/{co['id']}/week", params={"week_start": str(monday)}, headers=H).json()
    assert "R9.tool" not in {d["rule"] for d in w2["decisions"]}
