"""Component 1: intake produces product summary, ICP with embedding, voice samples;
ICP is editable with versioning. Crawl is mocked so tests run offline."""
import os

os.environ.setdefault("APP_ENV", "test")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db import engine, migrate
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
    def fake_crawl(root, extra=None, max_pages=12):
        return CrawlResult(root=root, pages=[{"url": root, "title": "Acme",
                                              "text": "Acme is an AI assistant for real estate agents. " * 20}])
    monkeypatch.setattr(pipeline, "crawl", fake_crawl)


def test_intake_end_to_end(client):
    co = client.post("/companies", json={"name": "Acme", "domain": "acme.example", "stage": "seed"}, headers=H).json()
    f = client.post(f"/companies/{co['id']}/founders",
                    json={"name": "Jane", "linkedin_handle": "jane", "x_handle": "jane"}, headers=H).json()
    r = client.post(f"/companies/{co['id']}/intake", json={
        "site_url": "https://acme.example",
        "best_customers": [{"company": "Big Brokerage", "domain": "bigbrokerage.com", "role": "COO"},
                           {"company": "Mid Realty", "domain": "midrealty.com"},
                           {"company": "Local Homes", "domain": "localhomes.com"}],
    }, headers=H)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["pages_crawled"] == 1
    assert out["icp_id"]
    assert len(out["customer_similarity"]) == 3
    assert len(out["voice_profile_ids"]) == 1

    # embedding stored
    with engine.connect() as c:
        n = c.execute(text("SELECT count(*) FROM icp WHERE id=:id AND embedding IS NOT NULL"),
                      {"id": out["icp_id"]}).scalar()
    assert n == 1

    # voice profile has samples from past posts and the banned list
    v = client.get(f"/founders/{f['id']}/voice", headers=H).json()
    assert len(v["samples"]) == 10  # 5 per platform from FakeSocial
    assert "delve" in v["rules"]["banned_phrases"]

    # ICP is readable and editable with version bump
    icp = client.get(f"/companies/{co['id']}/icp", headers=H).json()
    assert icp["version"] == 1
    icp2 = client.patch(f"/companies/{co['id']}/icp",
                        json={"description": "Brokerage COOs at 500+ agent firms"}, headers=H).json()
    assert icp2["version"] == 2 and icp2["description"].startswith("Brokerage")

    # company is now active
    assert client.get(f"/companies/{co['id']}", headers=H).json()["status"] == "active"
