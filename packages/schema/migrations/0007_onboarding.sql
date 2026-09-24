-- 0007_onboarding.sql — web onboarding and billing (Component 14).

-- A setup session is the resumable wizard: created at signup, carries the step reached,
-- signed into the link the customer keeps. Becomes a company at step 1.
CREATE TABLE setup_session (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  token         text NOT NULL UNIQUE,               -- random, in the URL; the only credential during setup
  email         text NOT NULL,
  company_id    uuid REFERENCES company(id) ON DELETE SET NULL,
  founder_id    uuid REFERENCES founder(id) ON DELETE SET NULL,
  step          int NOT NULL DEFAULT 1,             -- 1 company · 2 customers · 3 connect · 4 phone · 5 preferences · 6 diagnostic · 7 pay · 8 done
  data          jsonb NOT NULL DEFAULT '{}',        -- answers so far
  completed_at  timestamptz,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX setup_session_email_idx ON setup_session(email);
CREATE TRIGGER setup_session_updated BEFORE UPDATE ON setup_session FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE subscription (
  company_id       uuid PRIMARY KEY REFERENCES company(id) ON DELETE CASCADE,
  provider         text NOT NULL DEFAULT 'stripe',
  customer_ref     text,
  subscription_ref text,
  plan             text NOT NULL CHECK (plan IN ('founder','team','growth')),
  status           text NOT NULL DEFAULT 'incomplete'
                   CHECK (status IN ('incomplete','trialing','active','past_due','canceled','paused')),
  current_period_end timestamptz,
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER subscription_updated BEFORE UPDATE ON subscription FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Encrypted OAuth tokens per founder per platform. Encryption is application-side (Fernet, key in env);
-- the column never holds plaintext.
CREATE TABLE oauth_token (
  founder_id   uuid NOT NULL REFERENCES founder(id) ON DELETE CASCADE,
  platform     text NOT NULL CHECK (platform IN ('linkedin','x')),
  handle       text,
  ciphertext   bytea NOT NULL,
  scopes       text[] NOT NULL DEFAULT '{}',
  expires_at   timestamptz,
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (founder_id, platform)
);
CREATE TRIGGER oauth_token_updated BEFORE UPDATE ON oauth_token FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- founder preferences (schedule mode)
ALTER TABLE founder ADD COLUMN IF NOT EXISTS schedule_mode text NOT NULL DEFAULT 'managed' CHECK (schedule_mode IN ('managed','approve_times'));
