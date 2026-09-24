-- 0004_tool.sql — free tools (Component 11). A tool is a spec rendered to one hosted page;
-- its leads are signup_source rows tagged with the tool slug.

CREATE TABLE tool (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id    uuid NOT NULL REFERENCES company(id) ON DELETE CASCADE,
  slug          text NOT NULL,
  name          text NOT NULL,
  kind          text NOT NULL CHECK (kind IN ('calculator','scorecard','generator','lookup')),
  spec          jsonb NOT NULL DEFAULT '{}',    -- {question, inputs[], logic{}, result{}, capture{}, data_source}
  status        text NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed','draft','published','retired')),
  rationale     text,
  published_at  timestamptz,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_id, slug)
);
CREATE TRIGGER tool_updated BEFORE UPDATE ON tool FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- tool usage events: a run (with inputs hashed) and a lead capture
CREATE TABLE tool_event (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tool_id     uuid NOT NULL REFERENCES tool(id) ON DELETE CASCADE,
  company_id  uuid NOT NULL REFERENCES company(id) ON DELETE CASCADE,
  kind        text NOT NULL CHECK (kind IN ('view','run','lead')),
  payload     jsonb NOT NULL DEFAULT '{}',
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX tool_event_tool_idx ON tool_event(tool_id, kind, created_at);
