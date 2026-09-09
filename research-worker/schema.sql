-- Research Intelligence store. §22, §24, §77, §78.
--
-- D1 rather than KV because every question we ask of this data is a query: claims for a
-- species at a set of zones, valid in a month, above a tier, not yet stale. See README.

CREATE TABLE IF NOT EXISTS claims (
  id                   TEXT PRIMARY KEY,       -- sha1(source_url|species|claim_text)
  species              TEXT NOT NULL,
  claim_type           TEXT NOT NULL,
  zone_ids             TEXT NOT NULL,          -- JSON array
  waterbody_ids        TEXT NOT NULL DEFAULT '[]',
  geographic_description TEXT DEFAULT '',
  claim                TEXT NOT NULL,
  source_url           TEXT NOT NULL,          -- §20: no source, no claim
  source_title         TEXT DEFAULT '',
  source_domain        TEXT NOT NULL,
  source_tier          TEXT NOT NULL,          -- A | B | C | D
  published_at         TEXT,                   -- ISO date or NULL
  retrieved_at         INTEGER NOT NULL,       -- epoch seconds
  valid_months         TEXT NOT NULL DEFAULT '[]',
  season               TEXT DEFAULT '',
  geographic_confidence REAL NOT NULL DEFAULT 0,
  seasonal_relevance   REAL NOT NULL DEFAULT 0,
  recency              REAL NOT NULL DEFAULT 0,
  source_quality       REAL NOT NULL DEFAULT 0,
  combined_confidence  REAL NOT NULL DEFAULT 0,
  safety_sensitive     INTEGER NOT NULL DEFAULT 0,
  superseded_by        TEXT                    -- §78: a fresher claim from the same source
);

CREATE INDEX IF NOT EXISTS claims_species ON claims(species, source_tier, retrieved_at);
CREATE INDEX IF NOT EXISTS claims_domain  ON claims(source_domain, claim_type);

-- §78 — dedupe key: the same assertion, from the same source, about the same water.
CREATE UNIQUE INDEX IF NOT EXISTS claims_natural
  ON claims(species, claim_type, source_url, substr(claim, 1, 160));

-- §77 — every search cycle is auditable: what we asked, who answered, what we kept and
-- what we threw away. Deliberately NOT a copy of the pages themselves.
CREATE TABLE IF NOT EXISTS searches (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  at           INTEGER NOT NULL,
  species      TEXT NOT NULL,
  zone_ids     TEXT NOT NULL,
  family       TEXT NOT NULL,
  query        TEXT NOT NULL,
  provider     TEXT NOT NULL,
  model        TEXT DEFAULT '',
  latency_ms   INTEGER DEFAULT 0,
  source_urls  TEXT NOT NULL DEFAULT '[]',
  accepted     INTEGER NOT NULL DEFAULT 0,
  rejected     INTEGER NOT NULL DEFAULT 0,
  reject_reasons TEXT NOT NULL DEFAULT '[]',
  tokens_in    INTEGER DEFAULT 0,
  tokens_out   INTEGER DEFAULT 0,
  error        TEXT
);

CREATE INDEX IF NOT EXISTS searches_at ON searches(at);

-- §43 — daily cost controls, one row per UTC day.
CREATE TABLE IF NOT EXISTS budget (
  day        TEXT PRIMARY KEY,   -- YYYY-MM-DD
  queries    INTEGER NOT NULL DEFAULT 0,
  tokens_in  INTEGER NOT NULL DEFAULT 0,
  tokens_out INTEGER NOT NULL DEFAULT 0,
  cache_hits INTEGER NOT NULL DEFAULT 0
);
