-- 0001_core.sql — the eleven tables. Every row carries company_id (except company), created_at, updated_at.
-- Principle 1: outcome schema before features. This migration exists before any feature does.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END; $$ LANGUAGE plpgsql;

-- ---------- company ----------
CREATE TABLE company (
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name                  text NOT NULL,
  domain                text,
  stage                 text CHECK (stage IN ('pre_seed','seed','series_a','series_b','later')),
  product_summary       text,
  product_data_sources  jsonb NOT NULL DEFAULT '[]',
  founders              jsonb NOT NULL DEFAULT '[]',
  plan_tier             text NOT NULL DEFAULT 'design_partner' CHECK (plan_tier IN ('design_partner','founder','team','growth')),
  status                text NOT NULL DEFAULT 'onboarding' CHECK (status IN ('onboarding','active','paused','churned')),
  created_at            timestamptz NOT NULL DEFAULT now(),
  updated_at            timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER company_updated BEFORE UPDATE ON company FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------- founder ----------
CREATE TABLE founder (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id        uuid NOT NULL REFERENCES company(id) ON DELETE CASCADE,
  name              text NOT NULL,
  email             text,
  linkedin_handle   text,
  x_handle          text,
  oauth_tokens      bytea,                        -- encrypted blob; never logged
  voice_profile_id  uuid,                         -- FK added after voice_profile exists
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX founder_company_idx ON founder(company_id);
CREATE TRIGGER founder_updated BEFORE UPDATE ON founder FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------- icp ----------
CREATE TABLE icp (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id      uuid NOT NULL REFERENCES company(id) ON DELETE CASCADE,
  description     text,
  best_customers  jsonb NOT NULL DEFAULT '[]',    -- [{company, person, role, why_they_bought}]
  firmographics   jsonb NOT NULL DEFAULT '{}',
  personas        jsonb NOT NULL DEFAULT '[]',
  embedding       vector(1536),
  version         int NOT NULL DEFAULT 1,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX icp_company_idx ON icp(company_id);
CREATE TRIGGER icp_updated BEFORE UPDATE ON icp FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------- voice_profile ----------
CREATE TABLE voice_profile (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id  uuid NOT NULL REFERENCES company(id) ON DELETE CASCADE,
  founder_id  uuid NOT NULL REFERENCES founder(id) ON DELETE CASCADE,
  samples     jsonb NOT NULL DEFAULT '[]',        -- [{text, platform, source: past_post|approved|edited, metrics}]
  rules       jsonb NOT NULL DEFAULT '{}',        -- {tone, casing, banned_phrases[], formats_allowed[], visual: {colors, fonts, logo_url}}
  embedding   vector(1536),
  version     int NOT NULL DEFAULT 1,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX voice_profile_founder_idx ON voice_profile(founder_id);
CREATE TRIGGER voice_profile_updated BEFORE UPDATE ON voice_profile FOR EACH ROW EXECUTE FUNCTION set_updated_at();
ALTER TABLE founder ADD CONSTRAINT founder_voice_profile_fk FOREIGN KEY (voice_profile_id) REFERENCES voice_profile(id) ON DELETE SET NULL;

-- ---------- plan (judgment layer output, one per company per week) ----------
CREATE TABLE plan (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id    uuid NOT NULL REFERENCES company(id) ON DELETE CASCADE,
  week_start    date NOT NULL,
  scorecard     jsonb NOT NULL DEFAULT '{}',      -- {founder_distribution:{score,fix,rationale}, icp_attention:..., search:..., launches:..., onboarding:...}
  sequence      jsonb NOT NULL DEFAULT '[]',      -- ordered channel plan for the next 90 days
  targets       jsonb NOT NULL DEFAULT '{}',      -- {impressions_icp: n, followers_icp: n, ...}
  generated_by  text NOT NULL CHECK (generated_by IN ('rules','llm','human')),
  rules_version text,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_id, week_start)
);
CREATE TRIGGER plan_updated BEFORE UPDATE ON plan FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------- job (every action the product proposes or takes) ----------
CREATE TABLE job (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id     uuid NOT NULL REFERENCES company(id) ON DELETE CASCADE,
  plan_id        uuid REFERENCES plan(id) ON DELETE SET NULL,
  founder_id     uuid REFERENCES founder(id) ON DELETE SET NULL,
  type           text NOT NULL CHECK (type IN ('post','reply','page','launch_task','outreach','site_change','tool','heartbeat')),
  channel        text CHECK (channel IN ('linkedin','x','web','email','internal')),
  format         text,                            -- one of the 12 post formats, or template id
  input          jsonb NOT NULL DEFAULT '{}',
  output         jsonb NOT NULL DEFAULT '{}',     -- {text, media[], ...}
  state          text NOT NULL DEFAULT 'pending' CHECK (state IN ('pending','approved','edited','rejected','executed','failed')),
  voice_match    real,                            -- 0..1 from the voice-match check
  scheduled_for  timestamptz,
  executed_at    timestamptz,
  platform_ref   text,                            -- id on LinkedIn/X/etc. once executed
  approval_diff  jsonb,                           -- what the founder changed (training signal)
  error          text,
  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now(),
  -- Core invariant: an executed job must have a platform_ref
  CONSTRAINT job_executed_has_ref CHECK (state <> 'executed' OR platform_ref IS NOT NULL)
);
CREATE INDEX job_company_state_idx ON job(company_id, state);
CREATE INDEX job_scheduled_idx ON job(scheduled_for) WHERE state = 'approved';
CREATE TRIGGER job_updated BEFORE UPDATE ON job FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------- metric (daily numbers, per job and per company) ----------
CREATE TABLE metric (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id  uuid NOT NULL REFERENCES company(id) ON DELETE CASCADE,
  job_id      uuid REFERENCES job(id) ON DELETE SET NULL,
  date        date NOT NULL,
  name        text NOT NULL,                      -- impressions | impressions_icp | followers | followers_icp | clicks | signups | pages_indexed | replies | ...
  value       numeric NOT NULL,
  source      text NOT NULL,                      -- linkedin_api | x_api | search_console | signup_widget | computed:v1
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_id, job_id, date, name, source)
);
CREATE INDEX metric_company_date_idx ON metric(company_id, date);
CREATE TRIGGER metric_updated BEFORE UPDATE ON metric FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------- account (the attention map) ----------
CREATE TABLE account (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id       uuid NOT NULL REFERENCES company(id) ON DELETE CASCADE,
  platform         text NOT NULL CHECK (platform IN ('linkedin','x')),
  handle           text NOT NULL,
  name             text,
  headline         text,
  org              text,
  cluster          text CHECK (cluster IN ('buyer','influencer','peer','community')),
  icp_match_score  real,
  follows_count    int,
  interaction      jsonb NOT NULL DEFAULT '{}',   -- {last_replied_at, replies, reactions, dm_sent, ...}
  embedding        vector(1536),
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_id, platform, handle)
);
CREATE INDEX account_company_score_idx ON account(company_id, icp_match_score DESC);
CREATE TRIGGER account_updated BEFORE UPDATE ON account FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------- page (page factory output) ----------
CREATE TABLE page (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id   uuid NOT NULL REFERENCES company(id) ON DELETE CASCADE,
  template_id  text NOT NULL,                     -- product_for_segment | competitor_alternative | use_case_with_data
  slug         text NOT NULL,
  title        text NOT NULL,
  data         jsonb NOT NULL DEFAULT '{}',       -- must contain at least one real data point
  html_ref     text,
  status       text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','approved','published','indexed')),
  published_at timestamptz,
  indexed_at   timestamptz,
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_id, slug)
);
CREATE TRIGGER page_updated BEFORE UPDATE ON page FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------- outcome (plan vs result — the training set) ----------
CREATE TABLE outcome (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id  uuid NOT NULL REFERENCES company(id) ON DELETE CASCADE,
  plan_id     uuid NOT NULL REFERENCES plan(id) ON DELETE CASCADE,
  week_start  date NOT NULL,
  targets     jsonb NOT NULL DEFAULT '{}',
  actuals     jsonb NOT NULL DEFAULT '{}',
  delta       jsonb NOT NULL DEFAULT '{}',
  approval_rate real,
  edit_rate     real,
  notes       text,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_id, week_start)
);
CREATE TRIGGER outcome_updated BEFORE UPDATE ON outcome FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------- signup_source ("how did you hear about us", owned by us) ----------
CREATE TABLE signup_source (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id          uuid NOT NULL REFERENCES company(id) ON DELETE CASCADE,
  signup_id           text,
  answer_text         text NOT NULL,
  classified_channel  text,                       -- linkedin | x | search | launch | referral | other
  classified_by       text,                       -- rules:v1 | llm:v1 | human
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX signup_source_company_idx ON signup_source(company_id, created_at);
CREATE TRIGGER signup_source_updated BEFORE UPDATE ON signup_source FOR EACH ROW EXECUTE FUNCTION set_updated_at();
