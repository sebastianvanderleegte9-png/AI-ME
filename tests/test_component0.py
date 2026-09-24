"""Component 0 tests: schema applies, API auth works, job lifecycle and the core
invariant hold, fakes behave. Runs against a real Postgres (compose or CI service)."""
import os
import uuid

os.environ.setdefault("APP_ENV", "test")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db import engine, migrate
from app.interfaces import FakeLLM, FakeSocial
from app.main import app

H = {"x-api-key": "dev-key"}


@pytest.fixture(scope="session", autouse=True)
def _migrated():
    migrate()


@pytest.fixture
def client():
    return TestClient(app)


def test_all_eleven_tables_exist():
    with engine.connect() as c:
        names = {r[0] for r in c.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname='public'"))}
    expected = {"company", "founder", "icp", "voice_profile", "plan", "job", "metric",
                "account", "page", "outcome", "signup_source"}
    assert expected <= names


def test_auth_required(client):
    assert client.get("/companies").status_code == 401
    assert client.get("/companies", headers=H).status_code == 200


def test_job_lifecycle_and_invariant(client):
    co = client.post("/companies", json={"name": "T", "stage": "seed"}, headers=H).json()
    job = client.post("/jobs", json={"company_id": co["id"], "type": "post", "channel": "x",
                                     "output": {"text": "hello"}}, headers=H).json()
    assert job["state"] == "pending"

    # editing stores a diff and moves to 'edited'
    r = client.post(f"/jobs/{job['id']}/decision",
                    json={"decision": "approve", "edited_output": {"text": "hello, world"}}, headers=H).json()
    assert r["state"] == "edited"

    # cannot decide twice
    assert client.post(f"/jobs/{job['id']}/decision", json={"decision": "reject"}, headers=H).status_code == 409

    # core invariant: executed ⇒ platform_ref
    with engine.begin() as c, pytest.raises(Exception):
        c.execute(text("UPDATE job SET state='executed', platform_ref=NULL WHERE id=:id"), {"id": job["id"]})


def test_reject_path(client):
    co = client.post("/companies", json={"name": "T2"}, headers=H).json()
    job = client.post("/jobs", json={"company_id": co["id"], "type": "reply", "channel": "linkedin"}, headers=H).json()
    r = client.post(f"/jobs/{job['id']}/decision", json={"decision": "reject"}, headers=H).json()
    assert r["state"] == "rejected"


def test_fakes_are_deterministic():
    llm = FakeLLM()
    a, b = llm.embed(["same", "same"], purpose="t")
    assert a == b and len(a) == 1536
    s = FakeSocial()
    res = s.publish(founder_id="f", channel="x", text="hi")
    assert res.platform_ref.startswith("fake-x-")
    assert s.stats(founder_id="f", channel="x", platform_ref=res.platform_ref).impressions > 0
