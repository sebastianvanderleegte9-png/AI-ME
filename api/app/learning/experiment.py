"""The A/B (Component 12). New companies are assigned to an arm by a hash of their id
(blind, stable, ~50/50). The rules engine plans 'rules' companies; the learned planner
plans 'learned' companies. Evaluation compares 4-week growth in impressions inside ICP
between arms with Welch's t-test. Promotion requires: learned mean growth higher,
p < 0.05, at least MIN_PER_ARM companies per arm with >= 4 weeks each. Until promoted,
'learned' is only ever applied inside the experiment; after promotion it becomes the
default and rules stay as the fallback (abstention path)."""
from dataclasses import dataclass
from datetime import date
import hashlib
import math
import statistics

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Company, CompanyWeek, ExperimentArm

EXPERIMENT = "judgment-v2-vs-rules-v1"
MIN_PER_ARM = 20
MIN_WEEKS = 4
ALPHA = 0.05


def assign(db: Session, company: Company, force: str | None = None) -> str:
    row = db.get(ExperimentArm, company.id)
    if row and not force:
        return row.arm
    arm = force or ("learned" if int(hashlib.sha256(str(company.id).encode()).hexdigest(), 16) % 2 else "rules")
    if row:
        row.arm = arm            # an explicit assignment overrides the hash (operators only; logged by the caller)
    else:
        db.add(ExperimentArm(company_id=company.id, arm=arm, experiment=EXPERIMENT))
    db.commit()
    return arm


def arm_of(db: Session, company: Company) -> str:
    row = db.get(ExperimentArm, company.id)
    return row.arm if row else "rules"


@dataclass
class ArmStats:
    n: int
    mean: float
    sd: float
    growths: list[float]


def _company_growth(rows: list[CompanyWeek]) -> float | None:
    """4-week growth: last week's impressions_icp over the first week's, across >= MIN_WEEKS rows."""
    rows = sorted(rows, key=lambda r: r.week_start)
    vals = [r.result.get("impressions_icp") for r in rows if r.result.get("impressions_icp") is not None]
    if len(vals) < MIN_WEEKS or not vals[0]:
        return None
    return vals[-1] / vals[0] - 1


def welch(a: list[float], b: list[float]) -> tuple[float, float]:
    """Welch's t and a two-sided p (normal approximation for df; fine at n >= 20)."""
    if len(a) < 2 or len(b) < 2:
        return 0.0, 1.0
    ma, mb = statistics.mean(a), statistics.mean(b)
    va, vb = statistics.variance(a), statistics.variance(b)
    se = math.sqrt(va / len(a) + vb / len(b)) or 1e-9
    t = (ma - mb) / se
    p = 2 * (1 - _phi(abs(t)))
    return t, p


def _phi(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def evaluate(db: Session) -> dict:
    by_company: dict = {}
    for r in db.scalars(select(CompanyWeek)):
        by_company.setdefault(r.company_id, []).append(r)
    arms: dict[str, list[float]] = {"rules": [], "learned": []}
    for cid, rows in by_company.items():
        arm = arm_of(db, db.get(Company, cid))
        g = _company_growth(rows)
        if g is not None:
            arms[arm].append(g)
    a, b = arms["learned"], arms["rules"]
    t, p = welch(a, b)
    def st(x):
        return {"n": len(x), "mean_growth": round(statistics.mean(x), 4) if x else None, "sd": round(statistics.stdev(x), 4) if len(x) > 1 else None}
    enough = len(a) >= MIN_PER_ARM and len(b) >= MIN_PER_ARM
    wins = enough and a and b and statistics.mean(a) > statistics.mean(b) and p < ALPHA
    return {"experiment": EXPERIMENT, "learned": st(a), "rules": st(b), "t": round(t, 3), "p": round(p, 4),
            "min_per_arm": MIN_PER_ARM, "min_weeks": MIN_WEEKS, "enough_data": enough, "learned_wins": bool(wins),
            "verdict": ("promote learned to default" if wins else "keep rules as default" if enough else f"keep running: need {MIN_PER_ARM} companies with {MIN_WEEKS}+ weeks per arm")}


def promoted(db: Session) -> bool:
    """Promotion is a stored fact so it survives restarts and can be revoked."""
    from ..models import Plan  # noqa: F401  (import kept local to avoid cycles)
    from sqlalchemy import text
    v = db.execute(text("SELECT value FROM setting WHERE key = 'judgment_default'")).scalar() if _has_setting_table(db) else None
    return v == "learned"


def set_default(db: Session, engine: str) -> None:
    from sqlalchemy import text
    db.execute(text("CREATE TABLE IF NOT EXISTS setting (key text PRIMARY KEY, value text NOT NULL, updated_at timestamptz NOT NULL DEFAULT now())"))
    db.execute(text("INSERT INTO setting (key, value) VALUES ('judgment_default', :v) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()"), {"v": engine})
    db.commit()


def _has_setting_table(db: Session) -> bool:
    from sqlalchemy import text
    return bool(db.execute(text("SELECT 1 FROM pg_tables WHERE tablename = 'setting'")).scalar())


def engine_for(db: Session, company: Company) -> str:
    """Which planner runs this company this week: promoted default, else its experiment arm."""
    if promoted(db):
        return "learned"
    return arm_of(db, company)
