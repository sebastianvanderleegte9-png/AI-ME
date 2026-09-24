-- 0003_relationship.sql — relationships (Component 9).
-- kind=joint_launch: two companies on the product, proposed by matching, accepted by both founders.
-- kind=outreach:     one company -> one external account from its attention map, a warm sequence.

CREATE TABLE relationship (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id       uuid NOT NULL REFERENCES company(id) ON DELETE CASCADE,
  kind             text NOT NULL CHECK (kind IN ('joint_launch','outreach')),
  partner_company_id uuid REFERENCES company(id) ON DELETE CASCADE,   -- joint_launch
  account_id       uuid REFERENCES account(id) ON DELETE CASCADE,     -- outreach
  state            text NOT NULL DEFAULT 'proposed'
                   CHECK (state IN ('proposed','accepted_by_us','accepted','declined','active','replied','done','cancelled')),
  score            real,
  reason           text,                          -- why the product proposed it
  plan             jsonb NOT NULL DEFAULT '{}',   -- joint: {hook, launch_id_us, launch_id_them}; outreach: {steps[], cluster}
  log              jsonb NOT NULL DEFAULT '[]',   -- [{at, event, detail}]
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX relationship_company_idx ON relationship(company_id, kind, state);
CREATE UNIQUE INDEX relationship_pair_idx ON relationship(LEAST(company_id, partner_company_id), GREATEST(company_id, partner_company_id))
  WHERE kind = 'joint_launch' AND state NOT IN ('declined','cancelled','done');
CREATE UNIQUE INDEX relationship_outreach_idx ON relationship(company_id, account_id)
  WHERE kind = 'outreach' AND state NOT IN ('declined','cancelled','done');
CREATE TRIGGER relationship_updated BEFORE UPDATE ON relationship FOR EACH ROW EXECUTE FUNCTION set_updated_at();
