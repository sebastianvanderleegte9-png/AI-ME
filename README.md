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
| 4 | Attention map | **done** — ICP-seeded account map, fit score + clusters, daily reply targets in the feed, cooldowns |
| 5 | Metrics and Friday report | **done** — daily pull, impressions-inside-ICP (icp_v1), signup-source widget, weekly outcome row, Friday report + share card |
| 6 | Sequencer (Judgment v1) | **done** — Monday re-plan from the outcome row; 8 named rules; settings steer the voice engine; overrides logged |
| 7 | Page factory | **done** — 3 templates, ICP/product-driven candidates, data-point-required generation, batch approval, hosted pages + sitemap + FAQ schema, indexed tracking |
| 8 | Launch kit | **done** — PH / feature-drop / joint playbooks expand into dated jobs; posts pre-drafted from the brief; checklist taps; close writes results; sequencer proposes launches |
| 9 | Relationship engine | **done** — v1 joint launches brokered between companies on the product (match → both accept → linked launches); v2 warm outreach sequences to influencers/peers, reply cancels the rest |
| 10 | Site and onboarding engine | **done** — 40-check audit (clarity / action / first session / trust), rewrites as site_change jobs, hosted variant + CMS export, activation tracking, scorecard reads the audit |
| 11 | Tool factory | **done** — three ideas/quarter from data assets + ICP questions; validated specs (calculator / scorecard / generator / lookup); one-page hosted tools with a safe evaluator; lead capture into signup_source; distribution posts; view/run/lead stats |
| 12 | Learned judgment | next |

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

## Attention map (Component 4)

```
POST /companies/{id}/attention-map   build/refresh from the ICP (personas + customers -> enrichment search -> score -> cluster)
GET  /companies/{id}/attention-map   ?cluster=buyer|influencer|peer|community &platform= &limit=
POST /founders/{id}/targets          {platforms[], per_platform} -> reply jobs (type=reply) in the feed, one live thread each
```

Targets favour buyers and influencers by ICP fit, skip anyone replied to in the last 7 days, and a reply that
adds nothing (no experience, number, disagreement or question) is skipped rather than drafted.

## Metrics and report (Component 5)

```
POST /companies/{id}/metrics/pull         daily: per-job stats + impressions_icp (method computed:icp_v1), followers, search, signups
GET  /companies/{id}/report               weekly rollup JSON (this vs last week, top posts, approval/edit, signup sources)
POST /companies/{id}/report/close-week    Friday: outcome row = plan targets vs actuals (the dataset)
GET  /companies/{id}/report.html          the Friday email body
GET  /companies/{id}/report/card.png      1200x630 share card: one number, one delta
POST /public/{id}/signup-source           {answer, signup_id?} -> classified channel (no api key)
GET  /public/{id}/signup-widget.js        one <script> tag; adds 'how did you hear about us?' to any form[data-me-signup]
```

impressions_icp = impressions x share of engaged accounts matching the attention map (>= 0.5 fit); a 20% prior
is used and labelled when fewer than 5 engaged accounts are visible. The method id is on every row.
Worker tasks: `daily_metrics_pull` (daily), `friday_close` (Fridays), alongside `publish_due`.

## Sequencer (Component 6)

```
POST /companies/{id}/week            Monday re-plan (idempotent per week): settings + decisions with rule ids and reasons
GET  /companies/{id}/week            current weekly plan
POST /companies/{id}/week/override   {changes, reason, by} -> applied and logged as a labeled example
```

Rules (`judgment/sequencer.py`, seq-v1.0): R1 phase from the 90-day sequence · R2 attribution first · R3 approval
under 70% cuts volume and weights approved formats · R4 edit rate over 20% flags voice retraining · R5 two flat
weeks with good approval shifts to ICP-reaching formats and adds replies · R6 momentum holds the mix · R7 search
in phase + data asset schedules a page batch · R8 launches in phase opens the launch kit. The interview endpoint
picks up the week's settings automatically.

## Page factory (Component 7)

```
GET  /page-templates                          product_for_segment · competitor_alternative · use_case_with_data
POST /companies/{id}/pages/propose            {data_points:[{stat, source, tags[]}], limit} -> ranked candidates
POST /companies/{id}/pages/generate           same body (+ slugs? subset) -> drafts; rejected if < 350 words, banned phrase, or no data point in the text
GET  /companies/{id}/pages?status=            draft | published | indexed
POST /companies/{id}/pages/batch              {page_ids[], approve} -> publish or discard (the founder's one tap per batch)
POST /companies/{id}/pages/indexed            [slugs] -> mark indexed (Search Console hook)
GET  /p/{id}/{slug}   GET /p/{id}/sitemap.xml  public; drafts are never served
```

Rule: no data point, no page. Candidates are segments x personas x competitors x features from the ICP and product
summary; tagged data points route to matching pages.

## Launch kit (Component 8)

```
GET  /launch-playbooks                        product_hunt (ph-v1, T-42..T+7) · feature_drop (drop-v1) · joint (joint-v1)
POST /companies/{id}/launches                 {type, name, launch_date?, founder_id?, brief{what, why_now, hook, proof[], number?, customer?, target_signups}}
GET  /launches/{id}                           launch + calendar (every task/post with date, state, text)
POST /launches/{id}/expand                    (re)expand the playbook; idempotent
POST /launches/{id}/close                     results from the metrics tables for launch week
```

Playbook posts are drafted by the voice engine from the brief and land in the approval feed with the rest; checklist
tasks complete on tap. Sequencer R8 proposes a launch (type + Tue/Wed date) when launches are in phase and none is open.

## Relationship engine (Component 9)

```
GET  /companies/{id}/relationships/matches              other companies on the product: ICP adjacent (0.25-0.85), product not competing, readiness
POST /companies/{id}/relationships/joint                {partner_company_id} -> proposal with a joint hook; visible to both founders
POST /relationships/{id}/decide                         {company_id, accept} -> when both accept, a joint-v1 launch is created for each company
GET  /companies/{id}/relationships/outreach/candidates  influencers / peers / communities from the attention map, not already in a sequence
POST /companies/{id}/relationships/outreach             {founder_id, account_ids?|limit} -> 4-step warm sequence (reply d0, reply d3, DM d7, follow-up d14) as jobs in the feed
POST /relationships/{id}/replied                        they answered: pending steps cancelled, state=replied
GET  /companies/{id}/relationships?kind=                + outreach stats (reply rate; gate 25%)
```

## Site and onboarding engine (Component 10)

```
POST /companies/{id}/site/audit          {url?, html?, walkthrough?} -> 40 checks scored by category; stored on the plan row
POST /companies/{id}/site/rewrite        audit + site_change jobs for failed copy checks (h1, subhead, title, CTA, signup fields, first screen, activation email)
GET  /companies/{id}/site/changes        proposals and their state
GET  /companies/{id}/site/export         approved changes as a copy block for any CMS
GET  /v/{id}/landing                     hosted variant assembled from approved changes (with the signup-source widget)
POST /public/{id}/activation             {signup_id} from the founder's app when a user reaches first value
GET  /companies/{id}/site/activation     signups vs activations, last 28 days
```

Checks live in `site/checks.py` (audit-v1): each is a named function with a title, weight, evidence and fix. A tap on a
site_change executes it (it becomes part of the variant/export). The scorecard's onboarding channel reads the latest audit.

## Tool factory (Component 11)

```
POST  /companies/{id}/tools/propose      three tool ideas (calculator / scorecard / generator / lookup) as validated specs, status proposed
GET   /companies/{id}/tools              tools with view / run / lead stats
PATCH /tools/{id}/spec                   edit the spec (re-validated: formulas allow only + - * / ( ) comparisons, numbers, input ids, 'strings')
POST  /tools/{id}/decide                 {approve} -> published + two distribution posts in the feed, or retired
GET   /t/{company}/{slug}                the tool: one self-contained page, logic evaluated in the browser without eval()
POST  /public/tools/{id}/event           view | run | lead (leads also become signup_source rows: channel tool:{slug})
```

Sequencer R9 proposes tools when search or launches are in phase and none is live.

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
