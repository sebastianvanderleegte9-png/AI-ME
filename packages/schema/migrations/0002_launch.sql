-- 0002_launch.sql — launches (Component 8). A launch is a dated event with a playbook;
-- its tasks are ordinary jobs (type=launch_task) linked back by launch_id in job.input.

CREATE TABLE launch (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id    uuid NOT NULL REFERENCES company(id) ON DELETE CASCADE,
  founder_id    uuid REFERENCES founder(id) ON DELETE SET NULL,
  type          text NOT NULL CHECK (type IN ('product_hunt','feature_drop','joint','customer_story')),
  name          text NOT NULL,
  launch_date   date NOT NULL,
  playbook      text NOT NULL,                     -- playbook id + version, e.g. ph-v1
  status        text NOT NULL DEFAULT 'planned' CHECK (status IN ('planned','active','launched','closed','cancelled')),
  brief         jsonb NOT NULL DEFAULT '{}',       -- {what, why_now, proof, hook, target_signups, partner?}
  results       jsonb NOT NULL DEFAULT '{}',       -- filled at close: signups, impressions_icp, upvotes, sources
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX launch_company_date_idx ON launch(company_id, launch_date);
CREATE TRIGGER launch_updated BEFORE UPDATE ON launch FOR EACH ROW EXECUTE FUNCTION set_updated_at();
