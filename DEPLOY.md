# Going live on Railway

This gets Aime running at a real public URL, on Railway's free-to-start plan, with today's
fake LinkedIn/X/Stripe/Outlook providers (so nothing posts publicly or charges a real card yet)
but a real database, a real domain, and real signups. "Going real" at the bottom covers swapping
each provider on once its account is approved.

Five pieces, all from the same codebase: **web** (the site + API), **worker** (executes approved
jobs), and five small **cron jobs** (the things that are meant to run on a schedule — right now
they only run if you call them by hand).

## 1. Get the code onto GitHub

Railway deploys from a GitHub repo, not a zip file. From your Mac, in the `marketing-engineer` folder:

```bash
cd path/to/marketing-engineer
git add -A
git commit -m "Ready for deploy"
```

Then create an empty repo at github.com/new (don't check "add a README" — you already have code),
and push:

```bash
git remote add origin https://github.com/YOUR-USERNAME/marketing-engineer.git
git branch -M main
git push -u origin main
```

## 2. Create the Railway project

1. [railway.app](https://railway.app) → sign up with GitHub → **New Project** → **Deploy from GitHub repo** → pick `marketing-engineer`.
2. Railway will try to deploy it immediately as one service — let it, we'll fix the settings next. Rename this first service **web** (its Settings tab, top).
3. **New** → **Database** → **Add PostgreSQL**. **New** → **Database** → **Add Redis**. Railway wires `DATABASE_URL` and `REDIS_URL` into every service in the project automatically — you don't type those two.
4. One catch: our `DATABASE_URL` needs the `+psycopg` driver suffix that Railway's default doesn't include. On the **web** service → Variables → add `DATABASE_URL` as a **reference** to `${{Postgres.DATABASE_URL}}`, then edit the value to insert `+psycopg` after `postgresql`: `postgresql+psycopg://...`. Same reference on the **worker** and cron services later.

## 3. Set the web service's variables

**web** service → Variables tab → paste in everything from `.env.production.example` in this repo,
filling in real values for:
- `API_KEY` — generate one: `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`
- `TOKEN_ENCRYPTION_KEY` — generate one: `python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. This is the key that encrypts every founder's LinkedIn/X/Outlook token at rest — don't reuse the dev default that's in the code.
- `PUBLIC_BASE_URL` — leave it as the `*.up.railway.app` URL Railway shows you for now; update it once you attach a real domain (step 5).
- `ANTHROPIC_API_KEY` — worth turning on now (`LLM_PROVIDER=anthropic`) so real drafts are Claude-written from day one, even while LinkedIn/X posting is still fake.

Leave `SOCIAL_PROVIDER`, `OAUTH_PROVIDER`, `BILLING_PROVIDER`, `MESSAGING_PROVIDER`,
`TRANSCRIPTION_PROVIDER`, `CALENDAR_PROVIDER`, `EMAIL_PROVIDER` all on `fake` for now — that's
the whole point of shipping this way first. Deploy. Once it's up, open the Railway-given URL and
you should see the real homepage; `/health` should return `{"ok": true, ...}`.

## 4. Add the worker

**New** → **Empty Service** → under Source, pick the same GitHub repo (`marketing-engineer`) again.
Rename it **worker**. Settings → Deploy → **Custom Start Command**:

```
rq worker publish generate metrics default --url $REDIS_URL
```

Variables tab → copy the same variables you set on **web** (Railway → Variables → "Raw Editor" →
paste is fastest) — the worker needs the same `DATABASE_URL`/`REDIS_URL` references and provider
settings, since `execute_job` runs there.

## 5. Add the five cron jobs

Each is its own tiny service — same repo, same image, a **Cron Schedule** instead of always-on,
and a one-line start command that calls the task directly (no queue involved, these run once and exit):

| Service name | Schedule (UTC) | Custom Start Command |
|---|---|---|
| cron-publish-due | `*/5 * * * *` (every 5 min) | `python -c "from workers.tasks import publish_due; publish_due()"` |
| cron-daily-metrics | `0 11 * * *` (7am ET) | `python -c "from workers.tasks import daily_metrics_pull; daily_metrics_pull()"` |
| cron-morning-briefs | `0 12 * * *` (8am ET) | `python -c "from workers.tasks import sms_morning_briefs; sms_morning_briefs()"` |
| cron-monday-replan | `0 11 * * 1` (Mon 7am ET) | `python -c "from workers.tasks import monday_replan; monday_replan()"` |
| cron-friday-close | `0 20 * * 5` (Fri 4pm ET) | `python -c "from workers.tasks import friday_close, sms_friday_numbers; friday_close(); sms_friday_numbers()"` |

For each: **New** → **Empty Service** → same GitHub repo → Settings → **Deploy** → toggle
**Cron Schedule** on, paste the schedule → **Custom Start Command** as above → copy the same
variables as **web**. (Schedules above assume US Eastern; adjust the UTC hours if that's wrong,
and revisit once you have founders in other timezones — the brief/close times are currently one
schedule for everyone, not per-founder-timezone.)

## 6. A real domain (optional, do this when ready)

Railway → **web** service → Settings → **Networking** → **Custom Domain** → follow its DNS
instructions (a CNAME at your registrar). Once it's verified, update `PUBLIC_BASE_URL` on **web**
and **worker** (setup links and booking links in texts/emails are built from this) and redeploy.

## Verify it's actually live

1. Visit the homepage at your Railway/custom URL.
2. `/start` → run through the wizard as a test founder → confirm the setup flow, the free
   scorecard, and (with `BILLING_PROVIDER=fake`) that Checkout still completes.
3. `curl https://your-url/health` → `{"ok": true, ...}`.
4. Check the **worker** service's logs show it connected to Redis and is waiting for jobs.
5. Manually trigger one cron job from its Railway page ("Trigger" button) and check its logs for
   a clean exit rather than an import/connection error.

## Going real: swapping in each provider

Nothing above needs to change to flip a provider on — only that service's environment variable
and its secrets. Each is independent; do them as each account is ready:

- **LinkedIn + X** (`social_provider=linkedin_x`, `oauth_provider=real`): register apps in the
  LinkedIn Developer Portal and the X Developer Portal, get `LINKEDIN_CLIENT_ID/SECRET` and
  `X_CLIENT_ID/SECRET`, set the OAuth redirect URI on both apps to
  `https://your-domain/setup/oauth/linkedin/callback` and `https://your-domain/setup/oauth/x/callback`
  respectively (the platform name is part of the path — `api/app/routers/onboarding.py`'s
  `/setup/oauth/{platform}/callback`). Both platforms require an app review before real posting
  scopes are granted — budget a few days.
- **Stripe** (`billing_provider=stripe`): create a real Stripe account, add the three price IDs
  (Founder/Team/Growth) as `STRIPE_PRICE_*`, `STRIPE_SECRET_KEY` (start with a test-mode key,
  switch to live once you've smoke-tested a real Checkout), and point a Stripe webhook at
  `https://your-domain/public/billing/webhook` for `STRIPE_WEBHOOK_SECRET`.
- **Outlook** (`oauth_provider=real`, `calendar_provider=microsoft`, `email_provider=microsoft`):
  register an app in the Azure/Microsoft Entra portal, get `MS_CLIENT_ID/SECRET`, set the redirect
  URI to `https://your-domain/setup/oauth/outlook/callback`.
- **Twilio** (`messaging_provider=twilio`) + **Whisper** (`transcription_provider=whisper`): a
  Twilio number pointed at `https://your-domain/sms/inbound`, plus `OPENAI_API_KEY` for
  transcribing voice memos.

Flip one env var + its secrets on the **web** and **worker** services, redeploy both, and that
channel goes from fake to real — nothing else in the code changes.
