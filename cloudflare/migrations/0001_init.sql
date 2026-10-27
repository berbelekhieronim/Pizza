-- The same schema as server/store.py (the smoke test checks that they match).
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS sessions (
    pid TEXT PRIMARY KEY,
    study TEXT NOT NULL DEFAULT '',          -- '' = the main study
    grp TEXT NOT NULL DEFAULT '',            -- group from the link
    source TEXT NOT NULL DEFAULT '',         -- recruitment source
    invite TEXT NOT NULL DEFAULT '',         -- personal invite token, if the session came from one
    cond TEXT NOT NULL DEFAULT '',
    stage TEXT NOT NULL DEFAULT 'intro',     -- intro / practice / build / typical / followup / done
    started TEXT NOT NULL,                   -- UTC, ISO 8601
    updated TEXT,
    finished TEXT,                           -- first time stage reached done
    seconds REAL,                            -- updated (or finished) - started
    restarts INTEGER NOT NULL DEFAULT 0,
    consent TEXT,
    n_pieces INTEGER,
    neuro TEXT NOT NULL DEFAULT ''           -- self-described neurotype codes, space-separated
);
CREATE INDEX IF NOT EXISTS sessions_study ON sessions(study, started);
CREATE INDEX IF NOT EXISTS sessions_stage ON sessions(stage);
CREATE INDEX IF NOT EXISTS sessions_grp ON sessions(grp);
CREATE INDEX IF NOT EXISTS sessions_source ON sessions(source);
CREATE TABLE IF NOT EXISTS fields (
    pid TEXT NOT NULL REFERENCES sessions(pid) ON DELETE CASCADE,
    name TEXT NOT NULL,
    value TEXT NOT NULL,
    updated TEXT,
    PRIMARY KEY (pid, name)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS invites (
    token TEXT PRIMARY KEY, study TEXT NOT NULL DEFAULT '', grp TEXT NOT NULL DEFAULT '', source TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '', created TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS invites_study ON invites(study);
CREATE TABLE IF NOT EXISTS study_keys (study TEXT PRIMARY KEY, key TEXT NOT NULL UNIQUE, created TEXT NOT NULL);
