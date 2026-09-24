# Marketing Engineer

The marketing engineer as software. A founder connects their product, ICP and accounts; the
product decides what to build first, writes in the founder's voice, maps where the ICP pays
attention, generates pages from product data, runs launches, and reports one number every Friday.

Build plan: `docs/Build-Plan-AI-Marketing-Engineer.pdf`. This repo follows it component by component.

## Status

| # | Component | State |
|---|-----------|-------|
| 0 | Schema and skeleton | **done** — 11 tables, API, queue, worker, fakes, tests, CI |
| 1 | Intake and ICP model | next |
| 2 | Scorecard (Judgment v0) | |
| 3 | Voice engine + approval feed (+ visuals) | |
| 4 | Attention map | |
| 5 | Metrics and Friday report | |
| 6 | Sequencer (Judgment v1) | |
| 7–12 | Page factory, launch kit, relationships, site/onboarding, tool factory, learned judgment | |

## Run it

```bash
make up          # postgres (pgvector), redis, api :8000, worker, metabase :3001
make heartbeat   # a job goes pending -> executed through the queue
make seed        # company #1: Simplicity AI
make test
```

Without Docker: run Postgres 16 + pgvector and Redis locally, then

```bash
pip install -r requirements.txt
export PYTHONPATH=$PWD/api:$PWD DATABASE_URL=postgresql+psycopg://me:me@localhost:5432/me
(cd api && uvicorn app.main:app --port 8000) &
rq worker publish generate metrics default &
python scripts/heartbeat.py
```

API docs at http://localhost:8000/docs. Every request needs `x-api-key: dev-key` until Component 1
replaces it with founder logins.

## Layout

```
packages/schema/migrations/   the source of truth: plain SQL, applied in order
api/app/
  models.py                   SQLAlchemy mirrors of the SQL
  schemas.py                  request/response shapes (OpenAPI -> TS types for /web)
  interfaces/                 LLM · Enrichment · Social · MetricsSource — abstract + Fake
  routers/                    /companies  /jobs (the approval feed)  /metrics
  queue.py                    RQ queues: publish, generate, metrics, default
workers/tasks.py              heartbeat, execute_job (refuses anything not approved/edited)
scripts/                      heartbeat.py, seed.py
tests/                        one file per component
web/                          Next.js app (Component 1)
```

## Rules that are already enforced

- A job can only be executed from `approved` or `edited` (worker guard) and an executed job must
  carry a `platform_ref` (DB CHECK). Nothing ships without a founder's tap.
- Every founder edit is stored as `approval_diff` on the job — the voice engine's training signal.
- Providers are chosen by env (`LLM_PROVIDER`, `ENRICHMENT_PROVIDER`, `SOCIAL_PROVIDER`); `fake`
  runs everything with no external accounts.
- One `outcome` row per company per week is the dataset; it exists before any feature does.
