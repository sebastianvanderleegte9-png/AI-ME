-- 0008_meetings.sql — Outlook (email + calendar) and meeting scheduling (Component 15).

-- A third OAuth platform alongside linkedin/x: Outlook, for personalized outreach email
-- and free/busy + event creation.
ALTER TABLE oauth_token DROP CONSTRAINT IF EXISTS oauth_token_platform_check;
ALTER TABLE oauth_token ADD CONSTRAINT oauth_token_platform_check CHECK (platform IN ('linkedin','x','outlook'));

-- A meeting the bot is negotiating on the founder's behalf: it proposes times by email,
-- the prospect picks one on a public booking page, the founder approves or denies by text,
-- and only then does a calendar event get created.
CREATE TABLE meeting (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id        uuid NOT NULL REFERENCES company(id) ON DELETE CASCADE,
  founder_id        uuid NOT NULL REFERENCES founder(id) ON DELETE CASCADE,
  job_id            uuid REFERENCES job(id) ON DELETE SET NULL,       -- the outreach email that led here, if any
  relationship_id   uuid REFERENCES relationship(id) ON DELETE SET NULL,
  prospect_name     text,
  prospect_email    text NOT NULL,
  subject           text NOT NULL,
  duration_minutes  int NOT NULL DEFAULT 30,
  state             text NOT NULL DEFAULT 'sent'
                    CHECK (state IN ('sent','awaiting_founder','confirmed','declined','blocked','canceled')),
  proposed_slots    jsonb NOT NULL DEFAULT '[]',    -- [{start,end}] offered to the prospect
  chosen_slot       jsonb,                          -- {start,end} the prospect picked
  confirmed_start   timestamptz,
  confirmed_end     timestamptz,
  calendar_event_ref text,
  booking_token     text NOT NULL UNIQUE,
  rounds            int NOT NULL DEFAULT 1,          -- how many times slots were (re)sent
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX meeting_founder_idx ON meeting(founder_id);
CREATE INDEX meeting_confirmed_idx ON meeting(founder_id, confirmed_start);
CREATE TRIGGER meeting_updated BEFORE UPDATE ON meeting FOR EACH ROW EXECUTE FUNCTION set_updated_at();
