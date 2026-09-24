"""Component 10: 40 checks score a site from pasted HTML + walkthrough; failed copy checks
become site_change jobs in the feed; approved changes assemble into a hosted variant and
an export; the scorecard's onboarding channel reads the audit; activation rate tracks."""
import os
os.environ.setdefault("APP_ENV", "test")

import pytest
from fastapi.testclient import TestClient

from app.db import migrate
from app.intake import pipeline
from app.intake.crawl import CrawlResult
from app.main import app
from app.site.checks import CHECKS, Snapshot, run, score

H = {"x-api-key": "dev-key"}

BAD_SITE = """<html><head><title>Home</title></head><body>
<h1>Reinventing the future of work with next-generation intelligent technology for everyone everywhere</h1>
<p>We empower organizations to unleash seamless transformation. Book a demo to learn more.</p>
<a href="/demo">Book a demo</a>
<p>Coming soon.</p>
<form action="/demo"><input name="name"><input name="company"><input name="company_size"><input name="phone"><input name="role"><input name="card_number"><input type="submit"></form>
</body></html>"""

GOOD_SITE = """<html><head><title>Elli — listing packets in one click for brokerages</title></head><body>
<h1>Listing packets in one click, for brokerage agents</h1>
<p>For COOs and agents at residential real estate brokerages. 1,300 agents onboarded in six weeks; 4 hours saved per packet. First packet in your first session, today.</p>
<a href="/signup">Start free</a> <a href="/pricing">Pricing: free for 5 agents</a> <a href="https://www.linkedin.com/in/juraj-gago">Founder</a>
<img src="/screenshot.png" alt="product demo screenshot">
<h2>How it works</h2><p>Paste an address. Get the packet.</p>
<h2>Customers</h2><p>Used by ONE Sotheby's. Trusted by Douglas Elliman.</p>
<h2>Security</h2><p>SOC 2, privacy first. © Simplicity a.s.</p>
<form data-me-signup action="/signup"><input name="email" type="email" required><input name="me_source"><input type="submit"></form>
</body></html>"""
WALK_GOOD = {"signup_steps": 1, "signup_fields": 2, "requires_card": False, "requires_call": False, "mobile_ok": True,
             "first_screen_after_signup": "Paste one listing address to see your packet draft, or try the sample data.",
             "activation_email_subject": "Your first packet is one paste away"}
WALK_BAD = {"signup_steps": 4, "signup_fields": 7, "requires_card": True, "requires_call": True, "mobile_ok": False,
            "first_screen_after_signup": "Welcome to the platform! Watch this 40 minute getting started video tour. Invite your team and upgrade to unlock. " * 3,
            "activation_email_subject": "Welcome to our platform"}


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
    f = client.post(f"/companies/{co['id']}/founders", json={"name": "Jane", "linkedin_handle": "jane"}, headers=H).json()
    client.post(f"/companies/{co['id']}/intake", json={"site_url": "https://acme.example", "best_customers": [{"company": "A", "domain": "a.com"}]}, headers=H)
    client.patch(f"/companies/{co['id']}/icp", json={"personas": [{"title": "COO"}, {"title": "agent"}], "firmographics": {"industry": ["brokerage"]}}, headers=H)
    client.post(f"/companies/{co['id']}/scorecard", headers=H)
    return co, f


def test_forty_checks_discriminate():
    assert len(CHECKS) == 40 and len({c.id for c, _ in CHECKS}) == 40
    from app.site.engine import snapshot
    bad = score(run(snapshot("https://bad.example", ["brokerage", "coo"], BAD_SITE, WALK_BAD)))
    good = score(run(snapshot("https://good.example", ["brokerage", "coo"], GOOD_SITE, WALK_GOOD)))
    assert bad["overall"] <= 3.5 and good["overall"] >= 8.0, (bad["overall"], good["overall"])
    assert set(bad["categories"]) == {"clarity", "action", "first_session", "trust"}
    assert "c17" in bad["categories"]["action"]["failed"] and "c17" not in good["categories"]["action"]["failed"]


def test_audit_rewrite_variant_export(client):
    co, f = _setup(client)
    rep = client.post(f"/companies/{co['id']}/site/audit", json={"url": "https://acme.example", "html": BAD_SITE, "walkthrough": WALK_BAD}, headers=H).json()
    assert rep["overall"] <= 3.5 and len(rep["checks"]) == 40 and rep["fetched"]
    failed = [c for c in rep["checks"] if not c["passed"]]
    assert all(c["fix"] and c["evidence"] for c in failed)

    rw = client.post(f"/companies/{co['id']}/site/rewrite", json={"html": BAD_SITE, "walkthrough": WALK_BAD}, headers=H).json()
    elems = {c["element"] for c in rw["created"]}
    assert {"hero_h1", "hero_sub", "first_screen", "activation_email", "signup_form"} <= elems
    assert "primary_cta" not in elems   # the bad site has a 'Book a demo' link, so c11 passes; no CTA rewrite
    assert all(c["proposal"] and c["why"] for c in rw["created"])
    # they are in the founder's feed as site_change jobs
    feed = client.get(f"/founders/{f['id']}/feed", headers=H).json()
    sc = [j for j in feed if j["format"] in elems]
    assert len(sc) >= 5
    # approve the h1 and cta: a tap executes (no publish)
    for j in sc:
        if j["format"] in ("hero_h1", "hero_sub"):
            d = client.post(f"/jobs/{j['id']}/decision", json={"decision": "approve"}, headers=H).json()
            assert d["state"] == "executed"
    ex = client.get(f"/companies/{co['id']}/site/export", headers=H).json()
    assert set(ex) == {"hero_h1", "hero_sub"}
    v = client.get(f"/v/{co['id']}/landing")
    assert v.status_code == 200 and ex["hero_h1"] in v.text and "data-me-signup" in v.text and "signup-widget.js" in v.text

    # the scorecard's onboarding channel now reads the audit
    sc2 = client.post(f"/companies/{co['id']}/scorecard", headers=H).json()["scorecard"]["onboarding"]
    assert "audit" in sc2["evidence"] or sc2["score"] <= 4
    # re-audit with the good site: score rises
    rep2 = client.post(f"/companies/{co['id']}/site/audit", json={"html": GOOD_SITE, "walkthrough": WALK_GOOD}, headers=H).json()
    assert rep2["overall"] > rep["overall"] + 4


def test_activation_rate(client):
    co, f = _setup(client)
    client.post(f"/companies/{co['id']}/metrics/pull", headers=H)   # fake signups today
    for i in range(3):
        assert client.post(f"/public/{co['id']}/activation", json={"signup_id": f"u{i}"}).status_code == 201
    a = client.get(f"/companies/{co['id']}/site/activation", headers=H).json()
    assert a["activations"] == 3 and a["signups"] > 0 and a["activation_rate"] is not None
