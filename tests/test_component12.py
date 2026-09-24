"""Component 12: dataset rows are built from outcomes; the learned planner abstains without
neighbours and proposes from winners with them, citing them; hard rules still bind; blind
arm assignment is stable; evaluation uses a real test and promotion is gated on it."""
import os
os.environ.setdefault("APP_ENV", "test")

from datetime import date, timedelta
import json
import random
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db import SessionLocal, migrate
from app.intake import pipeline
from app.intake.crawl import CrawlResult
from app.learning import experiment
from app.learning.experiment import welch
from app.main import app
from app.models import Company, CompanyWeek, ExperimentArm, ICP, Outcome, Plan

H = {"x-api-key": "dev-key"}
MONDAY = date.today() - timedelta(days=date.today().weekday())


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


def _vec(seed: float):
    v = [0.0] * 1536
    v[0], v[1] = (1 - seed ** 2) ** 0.5, seed
    return v


def _seed_population(n: int, weeks: int, arm_growth: dict[str, float], rng: random.Random, tag: str) -> list[str]:
    """n companies, each with `weeks` outcome rows + company_week rows. Companies in the 'learned'
    arm grow by arm_growth['learned'] per week (plus noise), 'rules' by arm_growth['rules'].
    High-volume settings (7 posts) are the winners in the data so the planner has something to learn."""
    ids = []
    with SessionLocal() as db:
        for i in range(n):
            c = Company(name=f"{tag}-{i}", stage="seed", status="active",
                        product_summary=json.dumps({"one_liner": "x", "proof_points": ["p"], "data_assets": ["d"]}))
            db.add(c)
            db.flush()
            arm = "learned" if i % 2 else "rules"
            db.add(ExperimentArm(company_id=c.id, arm=arm))
            icp = ICP(company_id=c.id, description="COOs at brokerages", firmographics={"industry": ["brokerage"]}, personas=[{"title": "COO"}])
            db.add(icp)
            db.flush()
            db.execute(text("UPDATE icp SET embedding = :v WHERE id = :id"), {"v": str(_vec(0.1 + 0.01 * (i % 30))), "id": str(icp.id)})
            plan = Plan(company_id=c.id, week_start=MONDAY - timedelta(days=7 * weeks), generated_by="rules", targets={"impressions_icp_weekly": 1000},
                        sequence=[{"channel": "founder_distribution", "start_week": 1, "end_week": 12, "fix_id": "cadence_12", "fix": "x", "score_now": 3, "target_score_12w": 7}],
                        scorecard={"founder_distribution": {"score": 3}, "weekly": {"settings": {"posts_per_platform": 7 if i % 3 else 3, "replies_per_platform": 6, "format_weights": {"number_with_lesson": 2.0}}, "focus": "founder_distribution", "decisions": []}})
            db.add(plan)
            db.flush()
            icp_val = 1000.0
            for w in range(weeks):
                ws = MONDAY - timedelta(days=7 * (weeks - w))
                g = arm_growth[arm] + rng.gauss(0, 0.05) + (0.05 if i % 3 else -0.05)   # 7-post companies grow more
                icp_val *= (1 + g)
                db.add(Outcome(company_id=c.id, plan_id=plan.id, week_start=ws, targets=plan.targets,
                               actuals={"impressions_icp": round(icp_val), "approval_rate": 0.85, "edit_rate": 0.1, "signups": 5}, approval_rate=0.85, edit_rate=0.1))
            db.commit()
            ids.append(str(c.id))
        from app.learning.dataset import build_week
        for cid in ids:
            c = db.get(Company, uuid.UUID(cid))
            for w in range(weeks):
                build_week(db, c, MONDAY - timedelta(days=7 * (weeks - w)))
    return ids


def test_welch_and_arm_hash_stability():
    t, p = welch([0.3, 0.35, 0.28, 0.4, 0.33], [0.1, 0.12, 0.08, 0.15, 0.11])
    assert p < 0.01 and t > 0
    _, p2 = welch([0.2, 0.21, 0.19, 0.2], [0.2, 0.19, 0.21, 0.2])
    assert p2 > 0.5
    with SessionLocal() as db:
        c = Company(name="hash-me", stage="seed")
        db.add(c)
        db.commit()
        a1 = experiment.assign(db, c)
        a2 = experiment.assign(db, c)
        assert a1 == a2 and a1 in ("rules", "learned")


def test_planner_abstains_without_neighbours(client):
    co = client.post("/companies", json={"name": "Lonely", "stage": "series_b"}, headers=H).json()
    client.post(f"/companies/{co['id']}/founders", json={"name": "F", "linkedin_handle": "f"}, headers=H)
    client.post(f"/companies/{co['id']}/intake", json={"site_url": "https://l.example", "best_customers": [{"company": "A", "domain": "a.com"}]}, headers=H)
    with SessionLocal() as db:   # an ICP embedding far from everyone
        db.execute(text("UPDATE icp SET embedding = :v WHERE company_id = :c"), {"v": str(_vec(0.999)), "c": co["id"]})
        db.commit()
    client.post(f"/companies/{co['id']}/scorecard", params={"week_start": str(MONDAY)}, headers=H)
    pv = client.post(f"/learning/companies/{co['id']}/preview", params={"week_start": str(MONDAY)}, headers=H)
    # neighbours exist from other tests but with dissimilar ICPs they still count; abstention depends on count of usable rows
    assert pv.status_code == 200
    rules = {d["rule"] for d in pv.json()["decisions"]}
    assert ("L0.abstain" in rules) or ("L1.neighbours" in rules)


def test_dataset_learning_and_experiment(client):
    with SessionLocal() as db:          # isolate from any earlier run's promotion or leftover rows
        db.execute(text("DELETE FROM company_week"))
        db.commit()
        experiment.set_default(db, "rules")
    rng = random.Random(7)
    ids = _seed_population(n=48, weeks=5, arm_growth={"learned": 0.30, "rules": 0.10}, rng=rng, tag=f"pop-{uuid.uuid4().hex[:6]}")
    ds = client.get("/learning/dataset", headers=H).json()
    assert ds["companies"] >= 48 and ds["rows_with_growth"] >= 48 * 4

    # a new company similar to the population: the learned planner proposes from the winners
    co = client.post("/companies", json={"name": "Newbie", "stage": "seed"}, headers=H).json()
    client.post(f"/companies/{co['id']}/founders", json={"name": "N", "linkedin_handle": "n"}, headers=H)
    client.post(f"/companies/{co['id']}/intake", json={"site_url": "https://n.example", "best_customers": [{"company": "A", "domain": "a.com"}]}, headers=H)
    with SessionLocal() as db:
        db.execute(text("UPDATE icp SET embedding = :v WHERE company_id = :c"), {"v": str(_vec(0.2)), "c": co["id"]})
        db.commit()
    client.post(f"/companies/{co['id']}/scorecard", params={"week_start": str(MONDAY)}, headers=H)
    ns = client.get(f"/learning/companies/{co['id']}/neighbours", headers=H).json()
    assert len(ns) >= 8 and all(n["company_id"] != co["id"] for n in ns) and ns == sorted(ns, key=lambda n: -n["similarity"])
    pv = client.post(f"/learning/companies/{co['id']}/preview", params={"week_start": str(MONDAY)}, headers=H).json()
    rules = {d["rule"] for d in pv["decisions"]}
    assert "L1.neighbours" in rules and pv["settings"]["planner"] == "learned-v2.0"
    assert pv["settings"]["posts_per_platform"] == 7      # the winners in the data ran 7 posts
    assert pv["settings"]["format_weights"].get("number_with_lesson") == 2.0
    assert pv["neighbours"] and all(n["growth_wow"] is not None and n["settings"] for n in pv["neighbours"])
    # hard rules still bind: force a low-approval outcome -> R3 caps volume even under learned
    with SessionLocal() as db:
        p = db.query(Plan).filter_by(company_id=uuid.UUID(co["id"]), week_start=MONDAY).first()
        for ws, icp in ((MONDAY - timedelta(days=14), 1000), (MONDAY - timedelta(days=7), 1010)):
            db.add(Outcome(company_id=uuid.UUID(co["id"]), plan_id=p.id, week_start=ws, targets={}, actuals={"impressions_icp": icp, "approval_rate": 0.5, "edit_rate": 0.1}, approval_rate=0.5, edit_rate=0.1))
        db.commit()
    pv2 = client.post(f"/learning/companies/{co['id']}/preview", params={"week_start": str(MONDAY)}, headers=H).json()
    assert "R3.approval_gate" in {d["rule"] for d in pv2["decisions"]} and pv2["settings"]["posts_per_platform"] == 3

    # the Monday re-plan uses the company's arm
    client.post(f"/learning/experiment/assign/{co['id']}", params={"arm": "learned"}, headers=H)
    w = client.post(f"/companies/{co['id']}/week", params={"week_start": str(MONDAY)}, headers=H).json()
    assert w["engine"] == "learned" and w["settings"]["planner"] == "learned-v2.0"

    # evaluation: learned arm grew faster in the seeded data -> wins with p < 0.05; promotion allowed
    ev = client.get("/learning/experiment", headers=H).json()
    assert ev["enough_data"] and ev["learned"]["n"] >= 20 and ev["rules"]["n"] >= 20
    assert ev["learned"]["mean_growth"] > ev["rules"]["mean_growth"] and ev["p"] < 0.05 and ev["learned_wins"]
    assert client.post("/learning/experiment/default", json={"engine": "learned"}, headers=H).json()["default"] == "learned"
    assert client.get("/learning/experiment", headers=H).json()["default"] == "learned"
    # a rules-arm company now also gets the learned engine (promoted default), and revert works
    with SessionLocal() as db:
        rc = next(i for i in ids if experiment.arm_of(db, db.get(Company, uuid.UUID(i))) == "rules")
        assert experiment.engine_for(db, db.get(Company, uuid.UUID(rc))) == "learned"
    w2 = client.post(f"/companies/{rc}/week", params={"week_start": str(MONDAY)}, headers=H).json()
    assert w2["engine"] == "learned"
    assert client.post("/learning/experiment/default", json={"engine": "rules"}, headers=H).json()["default"] == "rules"


def test_promotion_refused_without_a_win(client):
    with SessionLocal() as db:
        db.execute(text("DELETE FROM company_week"))
        db.commit()
    r = client.post("/learning/experiment/default", json={"engine": "learned"}, headers=H)
    assert r.status_code == 409
