-- 0005_learning.sql — learned judgment (Component 12).
-- experiment: which engine plans each company (blind assignment) and the running comparison.
-- company_week: one denormalised row per company per week = the training set the planner reads.

CREATE TABLE experiment_arm (
  company_id   uuid PRIMARY KEY REFERENCES company(id) ON DELETE CASCADE,
  arm          text NOT NULL CHECK (arm IN ('rules','learned')),
  assigned_at  timestamptz NOT NULL DEFAULT now(),
  experiment   text NOT NULL DEFAULT 'judgment-v2-vs-rules-v1'
);

CREATE TABLE company_week (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id       uuid NOT NULL REFERENCES company(id) ON DELETE CASCADE,
  week_start       date NOT NULL,
  arm              text,                              -- which engine planned this week
  features         jsonb NOT NULL DEFAULT '{}',       -- stage, icp cluster, channel scores, prior week metrics, settings used
  settings         jsonb NOT NULL DEFAULT '{}',       -- the weekly settings that ran
  result           jsonb NOT NULL DEFAULT '{}',       -- impressions_icp, delta_wow, approval_rate, signups
  embedding        vector(1536),                      -- ICP embedding at the time, for neighbour retrieval
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_id, week_start)
);
CREATE INDEX company_week_week_idx ON company_week(week_start);
CREATE TRIGGER company_week_updated BEFORE UPDATE ON company_week FOR EACH ROW EXECUTE FUNCTION set_updated_at();
