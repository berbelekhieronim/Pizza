"""The study server's database: one SQLite file (data/study.db) holding every session, the fields it saved, the
personal invite links and the per-study researcher keys.

- WAL mode: participants keep saving while researchers read or export; every write is one transaction.
- sessions: one row per participant, with summary columns kept up to date on each save (where they are, pieces,
  what they said they are, time taken, restarts), so the researcher page can filter and sort thousands of sessions.
- fields: one row per saved field (pz_final, pz_events, pzf_data, ...), exactly as the task sent it.
- invites, study_keys, meta (schema version, condition counters).
Read it from R with RSQLite, or with analysis/analyse.py study.db. Standard library only.
"""
import glob
import json
import os
import re
import secrets
import sqlite3
import threading
import time

SCHEMA_VERSION = 1
SCHEMA = """
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
"""
FIELD_RE = re.compile(r'^[a-z_]{2,40}$')
INVITE_CHARS = 'abcdefghjkmnpqrstuvwxyz23456789'     # no 0/o, 1/l/i: easy to read out or type
SORTABLE = ('pid', 'study', 'grp', 'source', 'neuro', 'cond', 'stage', 'n_pieces', 'started', 'seconds', 'restarts')
STAGES = ('intro', 'practice', 'build', 'typical', 'followup', 'done')
IDLE_MINUTES = 30            # an unfinished session with no save for this long counts as stopped (it can still resume)
ACTIVITY = ('active', 'stopped')   # extra values of the "where" filter, from the time of the last save


def idle_cutoff():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(time.time() - IDLE_MINUTES * 60))


def now():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def iso_seconds(a, b):
    try:
        return time.mktime(time.strptime(b[:19], '%Y-%m-%dT%H:%M:%S')) - time.mktime(time.strptime(a[:19], '%Y-%m-%dT%H:%M:%S'))
    except (TypeError, ValueError):
        return None


def summary_columns(fields):
    """Summary columns from the saved fields: pieces on the pizza, self-described neurotype, consent, restarts."""
    out = {}
    if 'pz_final' in fields:
        try:
            out['n_pieces'] = len(json.loads(fields['pz_final']))
        except (ValueError, TypeError):
            pass
    if 'pzf_data' in fields:
        try:
            out['neuro'] = ' '.join(((json.loads(fields['pzf_data']) or {}).get('about') or {}).get('neuro') or [])
        except (ValueError, TypeError, AttributeError):
            pass
    if 'consent' in fields:
        out['consent'] = fields['consent']
    if 'restarts' in fields:
        try:
            out['restarts'] = int(fields['restarts'])
        except ValueError:
            pass
    return out


class Store:
    def __init__(self, path):
        self.path = path
        self.local = threading.local()
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        db = self.db()
        db.executescript(SCHEMA)
        db.execute("INSERT OR IGNORE INTO meta VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))

    def db(self):
        """One connection per thread (the server answers each request in its own thread). Autocommit; writes use
        explicit IMMEDIATE transactions so two saves never interleave."""
        c = getattr(self.local, 'db', None)
        if c is None:
            c = sqlite3.connect(self.path, timeout=15, isolation_level=None)
            c.row_factory = sqlite3.Row
            c.execute('PRAGMA journal_mode=WAL')
            c.execute('PRAGMA synchronous=NORMAL')
            c.execute('PRAGMA foreign_keys=ON')
            c.execute('PRAGMA busy_timeout=15000')
            self.local.db = c
        return c

    def tx(self):
        return _Tx(self.db())

    # ---- sessions
    def get(self, pid):
        """A session as one dict: its columns (group = grp) plus every saved field, like the old JSON files."""
        db = self.db()
        row = db.execute('SELECT * FROM sessions WHERE pid = ?', (pid,)).fetchone()
        if row is None:
            return None
        rec = dict(row)
        rec['group'] = rec.pop('grp')
        for f in db.execute('SELECT name, value FROM fields WHERE pid = ?', (pid,)):
            rec[f['name']] = f['value']
        return rec

    def create(self, pid, study, grp, source, invite, cond):
        with self.tx() as db:
            db.execute('INSERT INTO sessions (pid, study, grp, source, invite, cond, started, updated) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                       (pid, study, grp[:60], source[:80], invite, cond[:60], now(), now()))

    def exists(self, pid):
        return self.db().execute('SELECT 1 FROM sessions WHERE pid = ?', (pid,)).fetchone() is not None

    def next_condition(self, study, conds):
        """Conditions assigned in turn, per study (an atomic counter)."""
        with self.tx() as db:
            k = 'cond_next:' + study
            row = db.execute('SELECT v FROM meta WHERE k = ?', (k,)).fetchone()
            n = int(row['v']) if row else 0
            db.execute('INSERT OR REPLACE INTO meta VALUES (?, ?)', (k, str(n + 1)))
        return conds[n % len(conds)]

    def save(self, pid, fields, stage):
        """Merges fields into a session (only names like pz_final; string values) and records where they are."""
        clean = {k: v for k, v in fields.items() if isinstance(k, str) and FIELD_RE.match(k) and isinstance(v, str)}
        t = now()
        with self.tx() as db:
            row = db.execute('SELECT started, finished, stage FROM sessions WHERE pid = ?', (pid,)).fetchone()
            if row is None:
                return False
            db.executemany('INSERT INTO fields (pid, name, value, updated) VALUES (?, ?, ?, ?) '
                           'ON CONFLICT(pid, name) DO UPDATE SET value = excluded.value, updated = excluded.updated',
                           [(pid, k, v, t) for k, v in clean.items()])
            st = stage if stage in STAGES else row['stage']
            finished = row['finished'] or (t if st == 'done' else None)
            cols = dict(summary_columns(clean), stage=st, updated=t, finished=finished,
                        seconds=iso_seconds(row['started'], finished or t))
            db.execute('UPDATE sessions SET %s WHERE pid = ?' % ', '.join('%s = ?' % k for k in cols), list(cols.values()) + [pid])
        return True

    # ---- querying for the researcher page
    @staticmethod
    def where(f):
        """SQL WHERE for a filter dict: study (None = all, '' = main), grp, source, stage, neuro (contains), q (pid
        contains), since / until (YYYY-MM-DD, by start date)."""
        sql, args = [], []
        if f.get('study') is not None:
            sql.append('study = ?'); args.append(f['study'])
        if f.get('stage') == 'active':
            sql.append("stage != 'done' AND updated >= ?"); args.append(idle_cutoff())
        elif f.get('stage') == 'stopped':
            sql.append("stage != 'done' AND (updated IS NULL OR updated < ?)"); args.append(idle_cutoff())
        for col in ('grp', 'source', 'stage', 'cond'):
            if col == 'stage' and f.get(col) in ACTIVITY:
                continue
            if f.get(col):
                sql.append('%s = ?' % col); args.append(f[col])
        if f.get('neuro'):
            sql.append("(' ' || neuro || ' ') LIKE ?"); args.append('%% %s %%' % f['neuro'])
        if f.get('q'):
            sql.append('pid LIKE ?'); args.append('%%%s%%' % f['q'])
        if f.get('since'):
            sql.append('started >= ?'); args.append(f['since'])
        if f.get('until'):
            sql.append('started < ?'); args.append(f['until'] + 'T99')
        return (' WHERE ' + ' AND '.join(sql)) if sql else '', args

    def query(self, f, sort='started', desc=True, limit=100, offset=0):
        w, a = self.where(f)
        sort = sort if sort in SORTABLE else 'started'
        db = self.db()
        total = db.execute("SELECT COUNT(*), SUM(stage = 'done') FROM sessions" + w, a).fetchone()
        rows = db.execute('SELECT * FROM sessions%s ORDER BY %s %s, pid LIMIT ? OFFSET ?' % (w, sort, 'DESC' if desc else 'ASC'),
                          a + [limit, offset]).fetchall()
        return [dict(r) for r in rows], total[0], total[1] or 0

    def distinct(self, col, study=None):
        w, a = self.where({'study': study})
        return [r[0] for r in self.db().execute('SELECT DISTINCT %s FROM sessions%s ORDER BY 1' % (col, w), a) if r[0] != '']

    def last_started(self, study):
        """When the newest session of a study (None = all) started."""
        w, a = self.where({'study': study})
        return self.db().execute('SELECT MAX(started) FROM sessions' + w, a).fetchone()[0]

    def median_seconds(self, study):
        """Median time taken by the finished sessions of a study (None = all)."""
        w, a = self.where({'study': study, 'stage': 'done'})
        v = sorted(r[0] for r in self.db().execute('SELECT seconds FROM sessions%s' % w, a) if r[0] is not None)
        return None if not v else (v[len(v) // 2] if len(v) % 2 else (v[len(v) // 2 - 1] + v[len(v) // 2]) / 2)

    def counts_by_study(self):
        """{study: (sessions, finished, built a pizza, in progress now)}; the rest of the unfinished ones have stopped."""
        return {r['study']: (r['n'], r['done'] or 0, r['built'] or 0, r['active'] or 0) for r in self.db().execute(
            "SELECT study, COUNT(*) n, SUM(stage = 'done') done, SUM(stage IN ('typical', 'followup', 'done')) built, "
            "SUM(stage != 'done' AND updated >= ?) active FROM sessions GROUP BY study", (idle_cutoff(),))}

    def records(self, f):
        """Every matching session as a dict with its fields (for exports and the analysis), oldest first."""
        w, a = self.where(f)
        pids = [r[0] for r in self.db().execute('SELECT pid FROM sessions%s ORDER BY started, pid' % w, a)]
        for pid in pids:
            yield self.get(pid)

    def signature(self, f):
        """(count, newest update) of the matching sessions: the reports are rebuilt when this changes."""
        w, a = self.where(f)
        r = self.db().execute('SELECT COUNT(*), MAX(updated) FROM sessions' + w, a).fetchone()
        return '%d|%s' % (r[0], r[1] or '')

    # ---- invites
    def create_invites(self, study, grp, source, note, count):
        made = []
        with self.tx() as db:
            for _ in range(count):
                while True:
                    tok = ''.join(secrets.choice(INVITE_CHARS) for _ in range(8))
                    if not db.execute('SELECT 1 FROM invites WHERE token = ? UNION SELECT 1 FROM sessions WHERE pid = ?', (tok, tok)).fetchone():
                        break
                db.execute('INSERT INTO invites VALUES (?, ?, ?, ?, ?, ?)', (tok, study, grp[:60], source[:80], note[:200], now()))
                made.append(tok)
        return made

    def invite(self, token):
        r = self.db().execute('SELECT * FROM invites WHERE token = ?', (token,)).fetchone()
        return dict(r) if r else None

    def invites(self, study=None):
        """Invites with their status (not opened / started / finished) from the session they started."""
        w, a = ('WHERE i.study = ?', [study]) if study is not None else ('', [])
        return [dict(r) for r in self.db().execute(
            'SELECT i.*, s.stage, s.started, s.updated FROM invites i LEFT JOIN sessions s ON s.pid = i.token %s ORDER BY i.created, i.token' % w, a)]

    # ---- per-study researcher keys
    def study_key(self, study):
        """The researcher key that sees only this study (made on first use)."""
        r = self.db().execute('SELECT key FROM study_keys WHERE study = ?', (study,)).fetchone()
        if r:
            return r['key']
        with self.tx() as db:
            key = secrets.token_urlsafe(12)
            db.execute('INSERT OR IGNORE INTO study_keys VALUES (?, ?, ?)', (study, key, now()))
        return self.db().execute('SELECT key FROM study_keys WHERE study = ?', (study,)).fetchone()['key']

    def reset_study_key(self, study):
        with self.tx() as db:
            db.execute('DELETE FROM study_keys WHERE study = ?', (study,))
        return self.study_key(study)

    def study_for_key(self, key):
        r = self.db().execute('SELECT study FROM study_keys WHERE key = ?', (key,)).fetchone()
        return r['study'] if r else None

    # ---- copies
    def backup(self, dest, study=None):
        """A consistent copy of the database (while participants keep saving). With a study, a copy holding only that
        study's sessions, fields and invites (and no researcher keys)."""
        if os.path.exists(dest):
            os.remove(dest)
        out = sqlite3.connect(dest)
        self.db().backup(out)
        if study is not None:
            out.execute('PRAGMA foreign_keys=ON')
            out.execute('DELETE FROM sessions WHERE study != ?', (study,))
            out.execute('DELETE FROM fields WHERE pid NOT IN (SELECT pid FROM sessions)')
            out.execute('DELETE FROM invites WHERE study != ?', (study,))
            out.execute('DELETE FROM study_keys')
            out.commit()
            out.execute('VACUUM')
        out.close()

    # ---- the files of earlier versions
    def import_files(self, data_dir):
        """Imports sessions (participants/*.json), invites (invites.json) and condition counters (_state.json) written
        by earlier versions of the server, once: sessions already in the database are left as they are. The files stay."""
        n = 0
        for path in sorted(glob.glob(os.path.join(data_dir, 'participants', '*.json'))):
            try:
                with open(path, encoding='utf-8') as fh:
                    rec = json.load(fh)
            except (OSError, ValueError):
                continue
            pid = rec.get('pid') or os.path.basename(path)[:-5]
            if self.exists(pid):
                continue
            with self.tx() as db:
                db.execute('INSERT INTO sessions (pid, study, grp, source, invite, cond, stage, started, updated) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                           (pid, rec.get('study', ''), rec.get('group', ''), rec.get('source', ''), rec.get('invite', ''), rec.get('cond', ''),
                            rec.get('stage') if rec.get('stage') in STAGES else 'intro', rec.get('started') or now(), rec.get('updated') or rec.get('started')))
                fields = {k: v for k, v in rec.items() if FIELD_RE.match(k) and isinstance(v, str)
                          and k not in ('pid', 'study', 'group', 'source', 'invite', 'cond', 'stage', 'started', 'updated')}
                db.executemany('INSERT OR IGNORE INTO fields VALUES (?, ?, ?, ?)', [(pid, k, v, rec.get('updated')) for k, v in fields.items()])
                finished = rec.get('updated') if rec.get('stage') == 'done' else None
                cols = dict(summary_columns(fields), finished=finished, seconds=iso_seconds(rec.get('started'), rec.get('updated')))
                db.execute('UPDATE sessions SET %s WHERE pid = ?' % ', '.join('%s = ?' % k for k in cols), list(cols.values()) + [pid])
            n += 1
        try:
            with open(os.path.join(data_dir, 'invites.json'), encoding='utf-8') as fh:
                inv = json.load(fh)
        except (OSError, ValueError):
            inv = {}
        with self.tx() as db:
            for tok, v in inv.items():
                db.execute('INSERT OR IGNORE INTO invites VALUES (?, ?, ?, ?, ?, ?)',
                           (tok, v.get('study', ''), v.get('group', ''), v.get('source', ''), v.get('note', ''), v.get('created') or now()))
        try:
            with open(os.path.join(data_dir, '_state.json'), encoding='utf-8') as fh:
                state = json.load(fh)
        except (OSError, ValueError):
            state = {}
        with self.tx() as db:
            for k, v in state.items():
                db.execute('INSERT OR IGNORE INTO meta VALUES (?, ?)', ('cond_next:' + ('' if k == 'next' else k), str(v)))
        return n


class _Tx:
    """BEGIN IMMEDIATE ... COMMIT (or ROLLBACK on an error)."""
    def __init__(self, db):
        self.db = db

    def __enter__(self):
        self.db.execute('BEGIN IMMEDIATE')
        return self.db

    def __exit__(self, kind, value, tb):
        self.db.execute('COMMIT' if kind is None else 'ROLLBACK')
        return False
