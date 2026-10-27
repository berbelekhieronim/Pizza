-- Cloudflare only: what the Worker has stored in R2 and how big it is, so that storage stays under its limit
-- (the R2 free tier is 10 GB; the Worker refuses uploads above R2_LIMIT_BYTES, 8 GB by default).
CREATE TABLE IF NOT EXISTS files (key TEXT PRIMARY KEY, size INTEGER NOT NULL, updated TEXT NOT NULL);
