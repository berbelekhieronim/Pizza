-- Cloudflare only: the minute check for new data reads MAX(updated); an index makes that one lookup.
CREATE INDEX IF NOT EXISTS sessions_updated ON sessions(updated);
