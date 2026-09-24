"""Component 7: candidates come from ICP + product; a page needs a real data point or it is
rejected; generated pages are drafts until the batch is approved; published pages serve
with FAQ schema and appear in the sitemap; indexed status is tracked."""
import os
os.environ.setdefault("APP_ENV", "test")

import pytest
from fastapi.testclient import TestClient

from app.db import migrate
from app.intake import pipeline
from app.intake.crawl import CrawlResult
from app.main import app
from app.models import Company

H = {"x-api-key": "dev-key"}
DP = [{"stat": "1,300 agents onboarded in six weeks", "source": "rollout data, ONE Sotheby's", "tags": ["brokerage", "onboarding"]},
      {"stat": "4 hours saved per listing packet", "source": "agent survey, n=212", "tags": ["listing", "cma"]}]


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
    client.post(f"/companies/{co['id']}/founders", json={"name": "Jane", "linkedin_handle": "jane"}, headers=H)
    client.post(f"/companies/{co['id']}/intake", json={"site_url": "https://acme.example", "best_customers": [{"company": "A", "domain": "a.com"}]}, headers=H)
    client.patch(f"/companies/{co['id']}/icp", json={"firmographics": {"industry": ["residential brokerage", "property management"]},
                 "personas": [{"title": "Broker owner"}]}, headers=H)
    # fake LLM returns an echo for the product summary; give it real structure so candidates exist
    from app.db import SessionLocal
    import json, uuid
    with SessionLocal() as db:
        c = db.get(Company, uuid.UUID(co["id"]))
        c.product_summary = json.dumps({"one_liner": "AI assistant for agents", "key_features": ["CMA prep", "listing packets"],
                                        "competitors_mentioned": ["GenericAI"], "data_assets": ["rollout metrics"]})
        db.commit()
    return co


def test_propose_generate_batch_serve(client):
    co = _setup(client)
    cands = client.post(f"/companies/{co['id']}/pages/propose", json={"data_points": DP}, headers=H).json()
    assert len(cands) >= 6
    assert {c["template"] for c in cands} == {"product_for_segment", "competitor_alternative", "use_case_with_data"}
    assert all(c["data_points"] for c in cands)
    # tagged data point routes to the matching page
    seg = next(c for c in cands if c["template"] == "product_for_segment" and "brokerage" in c["slug"])
    assert "1,300" in seg["data_points"][0]["stat"]

    g = client.post(f"/companies/{co['id']}/pages/generate", json={"data_points": DP, "limit": 8}, headers=H).json()
    assert len(g["generated"]) >= 6 and all(p["words"] >= 350 for p in g["generated"])
    drafts = client.get(f"/companies/{co['id']}/pages", params={"status": "draft"}, headers=H).json()
    assert len(drafts) == len(g["generated"])
    # drafts are not served, and are not in the sitemap
    assert client.get(f"/p/{co['id']}/{drafts[0]['slug']}").status_code == 404
    assert drafts[0]["slug"] not in client.get(f"/p/{co['id']}/sitemap.xml").text

    ids = [p["id"] for p in drafts[:3]]
    b = client.post(f"/companies/{co['id']}/pages/batch", json={"page_ids": ids, "approve": True}, headers=H).json()
    assert len(b["published"]) == 3
    html = client.get(f"/p/{co['id']}/{drafts[0]['slug']}")
    assert html.status_code == 200 and "FAQPage" in html.text and "1,300" in html.text or "4 hours" in html.text
    sm = client.get(f"/p/{co['id']}/sitemap.xml").text
    assert sm.count("<url>") == 3

    # discard the rest
    rest = [p["id"] for p in drafts[3:]]
    if rest:
        d = client.post(f"/companies/{co['id']}/pages/batch", json={"page_ids": rest, "approve": False}, headers=H).json()
        assert len(d["deleted"]) == len(rest)
    # indexed
    n = client.post(f"/companies/{co['id']}/pages/indexed", json=[drafts[0]["slug"], "nope"], headers=H).json()["marked"]
    assert n == 1
    assert client.get(f"/companies/{co['id']}/pages", params={"status": "indexed"}, headers=H).json()[0]["slug"] == drafts[0]["slug"]
    # re-propose skips existing slugs
    again = client.post(f"/companies/{co['id']}/pages/propose", json={"data_points": DP}, headers=H).json()
    assert drafts[0]["slug"] not in {c["slug"] for c in again}


def test_no_data_point_no_page(client):
    co = _setup(client)
    r = client.post(f"/companies/{co['id']}/pages/generate", json={"data_points": []}, headers=H)
    assert r.status_code == 422
