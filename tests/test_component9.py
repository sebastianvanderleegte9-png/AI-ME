"""Component 9: joint-launch matching excludes competitors and unrelated ICPs; proposal ->
both accept -> two linked joint launches; outreach starts a 4-step warm sequence in the
feed; a reply cancels the rest; follow-ups skip when replied."""
import os
os.environ.setdefault("APP_ENV", "test")

import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db import SessionLocal, engine, migrate
from app.intake import pipeline
from app.intake.crawl import CrawlResult
from app.main import app
from app.models import Company
from workers.tasks import execute_job

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
        root=root, pages=[{"url": root, "title": "T", "text": "software. " * 30}]))


def _company(client, name, summary, icp_vec_seed: float):
    co = client.post("/companies", json={"name": name, "stage": "seed"}, headers=H).json()
    f = client.post(f"/companies/{co['id']}/founders", json={"name": f"{name} founder", "linkedin_handle": name.lower(), "x_handle": name.lower()}, headers=H).json()
    client.post(f"/companies/{co['id']}/intake", json={"site_url": f"https://{name.lower()}.example", "best_customers": [{"company": "A", "domain": "a.com"}]}, headers=H)
    client.patch(f"/companies/{co['id']}/icp", json={"personas": [{"title": "COO"}], "firmographics": {"industry": ["brokerage"]}}, headers=H)
    # deterministic ICP embeddings so adjacency is controllable: a unit vector rotated by seed
    dim = 1536
    v = [0.0] * dim
    v[0], v[1] = (1 - icp_vec_seed ** 2) ** 0.5, icp_vec_seed
    with SessionLocal() as db:
        c = db.get(Company, uuid.UUID(co["id"]))
        c.product_summary = json.dumps(summary)
        db.execute(text("UPDATE icp SET embedding = :v WHERE company_id = :c"), {"v": str(v), "c": co["id"]})
        db.commit()
    return co, f


def test_matching_and_joint_launch(client):
    # A: brokerage AI. B: adjacent ICP (0.6 similarity), different product. C: near-identical ICP + same product => competitor. D: unrelated ICP.
    A, fa = _company(client, "Alpha", {"one_liner": "AI listing packets for agents", "proof_points": ["1,300 agents"], "competitors_mentioned": []}, 0.0)
    B, fb = _company(client, "Beta", {"one_liner": "mortgage pre-approval automation for brokerages", "proof_points": ["2,000 loans"], "competitors_mentioned": []}, 0.8)
    C, fc = _company(client, "Gamma", {"one_liner": "AI listing packets for agents", "proof_points": [], "competitors_mentioned": ["Alpha"]}, 0.1)
    D, fd = _company(client, "Delta", {"one_liner": "fleet telematics for trucking", "proof_points": [], "competitors_mentioned": []}, 0.999)
    m = client.get(f"/companies/{A['id']}/relationships/matches", headers=H).json()
    names = [x["name"] for x in m]
    assert "Beta" in names and "Gamma" not in names and "Delta" not in names
    beta = next(x for x in m if x["name"] == "Beta")
    assert 0.25 <= beta["icp_adjacency"] <= 0.85 and beta["readiness"] == 1.0

    r = client.post(f"/companies/{A['id']}/relationships/joint", json={"partner_company_id": B["id"]}, headers=H)
    assert r.status_code == 201, r.text
    rel = r.json()
    assert rel["state"] == "proposed" and rel["plan"]["hook"] and rel["partner"]["name"] == "Beta"
    # same pair cannot be proposed twice while open
    assert client.post(f"/companies/{A['id']}/relationships/joint", json={"partner_company_id": B["id"]}, headers=H).status_code == 422
    # competitor is refused
    assert client.post(f"/companies/{A['id']}/relationships/joint", json={"partner_company_id": C["id"]}, headers=H).status_code == 422

    # A accepts, then B accepts -> two launches
    d1 = client.post(f"/relationships/{rel['id']}/decide", json={"company_id": A["id"], "accept": True}, headers=H).json()
    assert d1["state"] == "accepted_by_us" and d1["plan"]["accepted_by"] == ["us"]
    d2 = client.post(f"/relationships/{rel['id']}/decide", json={"company_id": B["id"], "accept": True}, headers=H).json()
    assert d2["state"] == "active" and d2["plan"]["launch_id_us"] and d2["plan"]["launch_id_them"]
    la = client.get(f"/launches/{d2['plan']['launch_id_us']}", headers=H).json()
    lb = client.get(f"/launches/{d2['plan']['launch_id_them']}", headers=H).json()
    assert la["type"] == lb["type"] == "joint" and la["launch_date"] == lb["launch_date"]
    assert "Beta" in la["name"] and "Alpha" in lb["name"]
    assert len(la["calendar"]) == len(lb["calendar"]) >= 6
    # both founders see the launch posts in their own feeds
    assert any(j["launch"] for j in client.get(f"/founders/{fa['id']}/feed", headers=H).json())
    assert any(j["launch"] for j in client.get(f"/founders/{fb['id']}/feed", headers=H).json())
    # an outsider cannot decide
    assert client.post(f"/relationships/{rel['id']}/decide", json={"company_id": D["id"], "accept": True}, headers=H).status_code == 403


def test_outreach_sequence_and_reply_cancels(client):
    A, fa = _company(client, "Omega", {"one_liner": "x", "proof_points": ["p"], "competitors_mentioned": []}, 0.0)
    client.post(f"/companies/{A['id']}/attention-map", headers=H)
    # promote a few accounts to influencer so candidates exist
    with SessionLocal() as db:
        db.execute(text("UPDATE account SET cluster='influencer', follows_count=50000 WHERE company_id=:c AND id IN (SELECT id FROM account WHERE company_id=:c LIMIT 3)"), {"c": A["id"]})
        db.commit()
    cands = client.get(f"/companies/{A['id']}/relationships/outreach/candidates", headers=H).json()
    assert 1 <= len(cands) <= 5 and all(c["cluster"] in ("influencer", "peer", "community") for c in cands)

    out = client.post(f"/companies/{A['id']}/relationships/outreach", json={"founder_id": fa["id"], "limit": 2}, headers=H).json()
    assert len(out) == 2 and all(r["state"] == "active" and len(r["plan"]["steps"]) == 4 for r in out)
    rel = out[0]
    steps = rel["plan"]["steps"]
    assert [s["day"] for s in steps] == [0, 3, 7, 14] and [s["kind"] for s in steps] == ["reply", "reply", "outreach", "outreach"]
    feed = client.get(f"/founders/{fa['id']}/feed", headers=H).json()
    mine = [j for j in feed if j["id"] in {s["job_id"] for s in steps}]
    assert len(mine) == 4 and all(j["voice_match"] >= 0.62 and j["text"] for j in mine)

    # they reply after step 0 -> remaining steps cancelled
    d = client.post(f"/jobs/{steps[0]['job_id']}/decision", json={"decision": "approve"}, headers=H).json()
    assert d["state"] == "approved"
    r = client.post(f"/relationships/{rel['id']}/replied", params={"note": "asked for the data"}, headers=H).json()
    assert r["state"] == "replied"
    for s in steps[1:]:
        assert client.get(f"/jobs/{s['job_id']}", headers=H).json()["state"] == "rejected"
    # the same account cannot be started again while open; candidates exclude it
    assert rel["account"]["id"] not in {c["id"] for c in client.get(f"/companies/{A['id']}/relationships/outreach/candidates", headers=H).json()}
    st = client.get(f"/companies/{A['id']}/relationships", params={"kind": "outreach"}, headers=H).json()["outreach"]
    assert st["started"] == 2 and st["replied"] == 1 and st["reply_rate"] == 0.5


def test_followup_skips_when_replied(client):
    A, fa = _company(client, "Sigma", {"one_liner": "x", "proof_points": [], "competitors_mentioned": []}, 0.0)
    client.post(f"/companies/{A['id']}/attention-map", headers=H)
    with SessionLocal() as db:
        db.execute(text("UPDATE account SET cluster='peer' WHERE company_id=:c"), {"c": A["id"]})
        db.commit()
    rel = client.post(f"/companies/{A['id']}/relationships/outreach", json={"founder_id": fa["id"], "limit": 1}, headers=H).json()[0]
    followup = rel["plan"]["steps"][3]["job_id"]
    client.post(f"/relationships/{rel['id']}/replied", headers=H)
    # the follow-up was already cancelled by mark_replied; force the worker path on a fresh approved copy
    with SessionLocal() as db:
        from app.models import Job
        j = db.get(Job, uuid.UUID(followup))
        j.state = "approved"
        db.commit()
    assert execute_job(followup) == "skipped"
