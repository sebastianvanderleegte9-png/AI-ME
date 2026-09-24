# Marketing Engineer

The marketing engineer as software. A founder connects their product, ICP and accounts; the
product decides what to build first, writes in the founder's voice, maps where the ICP pays
attention, generates pages from product data, runs launches, and reports one number every Friday.

Build plan: `docs/Build-Plan-AI-Marketing-Engineer.pdf`. This repo follows it component by component.

## Status

| # | Component | State |
|---|-----------|-------|
| 0 | Schema and skeleton | **done** — 11 tables, API, queue, worker, fakes, tests, CI |
| 1 | Intake and ICP model | **done** — founders, crawl→product summary, 3 customers→ICP+embedding, voice samples, Anthropic provider |
| 2 | Scorecard (Judgment v0) | **done** — 5 rule-scored channels, fix library, 90-day sequence, targets, HTML + PDF diagnostic |
| 3 | Voice engine + approval feed (+ visuals) | **done** — transcript→claims→12 formats→voice-checked drafts→feed; scheduled publish; brand-colored data cards |
| 4 | Attention map | next |
| 5 | Metrics and Friday report | |
| 6 | Sequencer (Judgment v1) | |
| 7–12 | Page factory, launch kit, relationships, site/onboarding, tool factory, learned judgment | |

## Real LLM

Set `LLM_PROVIDER=anthropic` and `ANTHROPIC_API_KEY=...` in `.env`. Without them every LLM call returns a deterministic fake so the pipeline still runs end to end.

## Intake (Component 1)

```
POST /companies/{id}/founders        {name, linkedin_handle, x_handle}
POST /companies/{id}/intake          {site_url, docs_urls[], best_customers[3+], site_text?}
GET  /companies/{id}/icp             PATCH to edit (bumps version)
GET  /founders/{id}/voice            samples + rules (banned phrases etc.)
```

If a site blocks fetches, pass `site_text` with the pasted page copy.

## Scorecard (Component 2)

```
POST /companies/{id}/scorecard        generate (rules v0.1) -> plan row for this week
GET  /companies/{id}/scorecard        latest, JSON
GET  /companies/{id}/scorecard.html   the in-app page
GET  /companies/{id}/scorecard.pdf    the diagnostic a founder gets sent (needs node + playwright)
```

Rules live in `api/app/judgment/rules.py`; every threshold is a named function with a rationale. Bump `RULES_VERSION` when you change one.

## Voice engine (Component 3)

```
POST  /founders/{id}/interview       {transcript, platforms[], posts_per_platform, week_start?}
GET   /founders/{id}/feed            the approval feed (pending by default; ?state=all)
POST  /jobs/{id}/decision            {decision: approve|reject, edited_output?}  -> publishes at its slot
GET   /founders/{id}/voice/stats     approval / edit rates, overall and per format (gate: 70% / 20%)
PATCH /founders/{id}/voice/rules     casing, tone, banned phrases, formats_allowed, visual brand
GET   /jobs/{id}/visual.png          brand-colored card, only when the post carries a number/steps/quote
GET   /formats                       the 12 formats
```

Every draft passes `voice/check.py` (banned phrases → hard fail; slop patterns → penalties; similarity to the
founder's own posts) before it reaches the feed. Nothing publishes without a tap. Run `workers.tasks.publish_due`
every few minutes as the scheduler safety net.

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
