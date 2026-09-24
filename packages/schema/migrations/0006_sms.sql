-- 0006_sms.sql — the SMS surface (Component 13).
-- A founder binds a phone; every message in and out is logged; conversation state tracks
-- what "yes" refers to right now.

ALTER TABLE founder ADD COLUMN IF NOT EXISTS phone text;
ALTER TABLE founder ADD COLUMN IF NOT EXISTS phone_verified_at timestamptz;
ALTER TABLE founder ADD COLUMN IF NOT EXISTS timezone text NOT NULL DEFAULT 'America/New_York';
CREATE UNIQUE INDEX IF NOT EXISTS founder_phone_idx ON founder(phone) WHERE phone IS NOT NULL;

CREATE TABLE sms_message (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  founder_id   uuid REFERENCES founder(id) ON DELETE SET NULL,
  company_id   uuid REFERENCES company(id) ON DELETE SET NULL,
  direction    text NOT NULL CHECK (direction IN ('in','out')),
  phone        text NOT NULL,
  body         text NOT NULL DEFAULT '',
  media        jsonb NOT NULL DEFAULT '[]',        -- inbound: [{url, content_type, transcript?}]
  kind         text,                               -- out: brief|draft|reply_target|launch_task|site_change|tool_ideas|joint|friday|ack|clarify|setup|verify ; in: text|voice|command
  refs         jsonb NOT NULL DEFAULT '{}',        -- {job_ids[], relationship_id, tool_ids[], batch_id}
  provider_ref text,
  created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX sms_message_founder_idx ON sms_message(founder_id, created_at DESC);

CREATE TABLE sms_state (
  founder_id     uuid PRIMARY KEY REFERENCES founder(id) ON DELETE CASCADE,
  current        jsonb NOT NULL DEFAULT '{}',     -- {kind, job_id|relationship_id|tool_ids, sent_at}: what a bare yes/no applies to
  batch          jsonb NOT NULL DEFAULT '[]',     -- [{n, kind, job_id|...}] numbered items from the last brief
  pending_verify text,                            -- 6-digit code awaiting reply
  quiet_hours    jsonb NOT NULL DEFAULT '{"start": 21, "end": 7}',
  brief_hour     int NOT NULL DEFAULT 8,
  paused         boolean NOT NULL DEFAULT false,
  updated_at     timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER sms_state_updated BEFORE UPDATE ON sms_state FOR EACH ROW EXECUTE FUNCTION set_updated_at();
