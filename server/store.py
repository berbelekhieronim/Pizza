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
    stage TEXT NOT NULL DEFAULT 'intro',     -- intro / survey / practice / build / typical / followup / done / declined
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
SORTABLE = ('pid', 'study', 'grp', 'source', 'neuro', 'cond', 'stage', 'n_pieces', 'started', 'updated', 'seconds', 'restarts')
# survey: the study's questions asked before the pizza (study setting survey_when = before); followup: after it
STAGES = ('intro', 'survey', 'practice', 'build', 'typical', 'followup', 'done', 'declined')   # declined: said no to the consent
IDLE_MINUTES = 30            # an unfinished session with no save for this long counts as stopped (it can still resume)
ACTIVITY = ('active', 'stopped')   # extra values of the "where" filter, from the time of the last save
ANALYSIS = ('included', 'pending', 'left_out', 'flagged', 'synthetic', 'real', 'analysed', 'in_progress', 'excluded', 'abandoned', 'no_pizza')  # ... from whether the session's pizza is analysed, needs a look, or is synthetic
SYN_SQL = "pid LIKE 'SYN-%'"        # synthetic sessions of a test study (analysis/synthetic.py): ids SYN-001 ...
# The researcher's choice for a session (field 'inclusion', never taken from a participant's save): 'include',
# 'exclude' or 'auto' (kept, so that going back to automatic also rebuilds the reports); no field = automatic: a session past the build (its own pizza finished) is analysed, one that stopped
# with a pizza started is left out (analysis/analyse.py applies the same rule)
INCLUSION = 'inclusion'
INCLUSION_VALUES = ('include', 'exclude', 'auto')
INCL_SQL = "COALESCE((SELECT NULLIF(value, 'auto') FROM fields WHERE fields.pid = sessions.pid AND name = 'inclusion'), '')"
# saved by the participant page (from 0.13.0): the browser, system and time zone, and any trouble saving or in the page;
# listed with each session, read from the fields (no extra columns, so nothing to migrate)
CLIENT_FIELDS = ('browser', 'os', 'tz', 'browser_flags', 'translated', 'save_fails', 'client_errors')
CLIENT_SQL = ', '.join("(SELECT value FROM fields WHERE fields.pid = sessions.pid AND name = '%s') AS %s" % (k, k) for k in CLIENT_FIELDS)
# The automatic rule, the same as analysis/analyse.py: a session's own pizza is analysed when it was finished (the
# participant pressed "I'm done": its summary is not "finished": false; the stage is not used, because a tab closed
# while the pizza bakes, or two saves arriving out of order, can leave a finished pizza at stage "build"), unless the
# browser was driven by a program (browser_flags in AUTO_EXCLUDE_FLAGS). The researcher's choice overrides both.
AUTO_EXCLUDE_FLAGS = ('automated',)
# finished: the pizza's summary says so, or the session got past the build (the next part only opens after "I'm done",
# so a pizza whose last saves were lost on the way still counts as submitted, as last saved; analyse.py SUBMITTED_STAGES)
FINISHED_SQL = ("(stage IN ('typical', 'followup', 'done') OR (COALESCE((SELECT value FROM fields WHERE fields.pid = sessions.pid AND name = 'pz_summary'), '') NOT LIKE '%\"finished\":false%' "
                "AND COALESCE((SELECT value FROM fields WHERE fields.pid = sessions.pid AND name = 'pz_summary'), '') NOT LIKE '%\"finished\": false%'))")
FLAGGED_OUT_SQL = '(' + ' OR '.join("(' ' || COALESCE((SELECT value FROM fields WHERE fields.pid = sessions.pid AND name = 'browser_flags'), '') || ' ') LIKE '%% %s %%'" % f
                                    for f in AUTO_EXCLUDE_FLAGS) + ')'
AUTO_IN_SQL = '(n_pieces IS NOT NULL AND ' + FINISHED_SQL + ' AND NOT ' + FLAGGED_OUT_SQL + ')'
# An unfinished pizza (no "I'm done" yet) is PENDING while its session saved within ABANDON_HOURS: the participant may
# still be building, or come back (reload, the same link). After that it counts as abandoned and is left out. Neither
# is analysed (an unfinished pizza is not a choice); pending ones are listed with the sessions in progress, never as
# excluded. (The same in the Worker, cloudflare/src/store.js, and analysis/analyse.py ABANDON_HOURS.)
ABANDON_HOURS = 24
PENDING_SQL = ('(' + INCL_SQL + " = '' AND n_pieces IS NOT NULL AND NOT " + FINISHED_SQL + " AND NOT " + FLAGGED_OUT_SQL
               + " AND stage NOT IN ('done', 'declined') AND updated >= strftime('%Y-%m-%dT%H:%M:%SZ', 'now', '-" + str(ABANDON_HOURS) + " hours'))")
LEFT_OUT_SQL = '(' + INCL_SQL + " = 'exclude' OR (" + INCL_SQL + " = '' AND n_pieces IS NOT NULL AND NOT " + AUTO_IN_SQL + ' AND NOT ' + PENDING_SQL + '))'
INCLUDED_SQL = '(' + INCL_SQL + " = 'include' OR (" + INCL_SQL + " = '' AND " + AUTO_IN_SQL + '))'
# the Sessions tab's groups: 0 analysed, 1 in progress now (unfinished, saved within IDLE_MINUTES; a pizza being built
# shows here), 2 the rest (left out, stopped, no pizza, declined), folded away under a button. One ? = idle_cutoff().
# Every session has exactly one status (one ? = idle_cutoff()); the researcher page's tiles count them (they add up
# to "opened the link"), its Sessions tab groups and labels by them, the Worker uses the same (store.js STATUS_SQL):
#   analysed       its pizza is in the reports (finished, or included by the researcher)
#   active         no pizza yet, saved within IDLE_MINUTES (reading, answering, practising)
#   pending        a pizza not finished yet, saved within ABANDON_HOURS (they may still finish it)
#   excluded       left out by the researcher;  excluded_auto  left out automatically (a program drove the browser)
#   abandoned      a pizza never finished, no save for ABANDON_HOURS
#   no_pizza       left before building a pizza (consent, questions, practice)
#   declined       said no to the consent
STATUSES = ('analysed', 'active', 'pending', 'excluded', 'excluded_auto', 'abandoned', 'no_pizza', 'declined')
STATUS_SQL = ("(CASE WHEN stage = 'declined' THEN 'declined' "
              "WHEN n_pieces IS NULL THEN (CASE WHEN stage != 'done' AND updated >= ? THEN 'active' ELSE 'no_pizza' END) "
              "WHEN " + INCLUDED_SQL + " THEN 'analysed' WHEN " + INCL_SQL + " = 'exclude' THEN 'excluded' "
              "WHEN " + PENDING_SQL + " THEN 'pending' WHEN " + FLAGGED_OUT_SQL + " THEN 'excluded_auto' ELSE 'abandoned' END)")
# the Sessions tab's groups: 0 in the reports, 1 in progress (active or pending), 2 the rest (folded); one ?
LIST_GROUP_SQL = "(CASE " + STATUS_SQL + " WHEN 'analysed' THEN 0 WHEN 'active' THEN 1 WHEN 'pending' THEN 1 ELSE 2 END)"
# browser trouble worth a look before analysing (participant page, docs/BROWSERS.md): the "needs a look" filter
REVIEW_FLAGS = ('translated', 'coarse-timer', 'forced-colors', 'automated')    # small-window: information only from 0.18.1 (the task waits until it fits)
# page errors other than Chrome's "ResizeObserver loop" notice (harmless; no longer recorded from 0.18.1): more entries
# (each ends with "]) than mentions of the notice
REAL_ERRORS_SQL = "(LENGTH(value) - LENGTH(REPLACE(value, '\"]', ''))) / 2 > (LENGTH(value) - LENGTH(REPLACE(value, 'ResizeObserver loop', ''))) / 19"
REVIEW_SQL = '(' + ' OR '.join("(' ' || COALESCE((SELECT value FROM fields WHERE fields.pid = sessions.pid AND name = 'browser_flags'), '') || ' ') LIKE '%% %s %%'" % f
                               for f in REVIEW_FLAGS) + " OR EXISTS (SELECT 1 FROM fields WHERE fields.pid = sessions.pid AND name = 'client_errors' AND " + REAL_ERRORS_SQL + "))"
# what the analysis does with a session: included / left_out / no_pizza (shown on the Sessions tab and in sessions.csv)
ANALYSIS_SQL = "CASE WHEN n_pieces IS NULL THEN 'no_pizza' WHEN %s THEN 'included' WHEN %s THEN 'pending' ELSE 'left_out' END" % (INCLUDED_SQL, PENDING_SQL)


def idle_cutoff():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(time.time() - IDLE_MINUTES * 60))


def now():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def iso_seconds(a, b):
    try:
        return time.mktime(time.strptime(b[:19], '%Y-%m-%dT%H:%M:%S')) - time.mktime(time.strptime(a[:19], '%Y-%m-%dT%H:%M:%S'))
    except (TypeError, ValueError):
        return None


STAGE_RANK = {'intro': 0, 'survey': 1, 'practice': 2, 'build': 3, 'typical': 4, 'followup': 5, 'done': 6, 'declined': 6}


def later_stage(old, new):
    """The stage a save leaves a session at: never an earlier one. Saves can arrive out of order (the save at the end of
    a part and the first of the next go out together; a closing tab's save comes late), and an older one must not move
    a finished session back to 'build'. 'done' and 'declined' are final. (Same as laterStage in the Worker.)"""
    if new not in STAGES:
        return old
    if old not in STAGE_RANK:
        return new
    return new if STAGE_RANK[new] > STAGE_RANK[old] else old


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



def stale_save(new, old):
    """True when save_seq new ("<page load>:<n>") is older than the stored one from the same page load."""
    try:
        a, b = (new or '').split(':'), (old or '').split(':')
        return len(a) == 2 and len(b) == 2 and a[0] == b[0] and int(a[1]) < int(b[1])
    except ValueError:
        return False

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

    def save(self, pid, fields, stage):  # noqa: C901
        """Merges fields into a session (only names like pz_final; string values) and records where they are."""
        clean = {k: v for k, v in fields.items() if isinstance(k, str) and FIELD_RE.match(k) and k != INCLUSION and isinstance(v, str)}
        t = now()
        with self.tx() as db:
            row = db.execute('SELECT started, finished, stage FROM sessions WHERE pid = ?', (pid,)).fetchone()
            if row is None:
                return False
            # a save older than one already stored from the same page (they can arrive out of order) changes nothing:
            # save_seq = "<page load id>:<count>" (participate.html); another page load (a reload) always counts
            if stale_save(clean.get('save_seq'), (db.execute("SELECT value FROM fields WHERE pid = ? AND name = 'save_seq'", (pid,)).fetchone() or {'value': None})['value']):
                clean = {}
            db.executemany('INSERT INTO fields (pid, name, value, updated) VALUES (?, ?, ?, ?) '
                           'ON CONFLICT(pid, name) DO UPDATE SET value = excluded.value, updated = excluded.updated',
                           [(pid, k, v, t) for k, v in clean.items()])
            st = later_stage(row['stage'], stage)
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
            sql.append("stage NOT IN ('done', 'declined') AND updated >= ?"); args.append(idle_cutoff())
        elif f.get('stage') == 'stopped':
            sql.append("stage NOT IN ('done', 'declined') AND (updated IS NULL OR updated < ?)"); args.append(idle_cutoff())   # a refusal is counted on its own (stage declined)
        elif f.get('stage') == 'included':
            sql.append(INCLUDED_SQL)
        elif f.get('stage') == 'left_out':
            sql.append(LEFT_OUT_SQL)
        elif f.get('stage') == 'pending':
            sql.append(PENDING_SQL)
        elif f.get('stage') in ('analysed', 'in_progress', 'excluded', 'abandoned', 'no_pizza'):     # by status (the tiles)
            want = {'in_progress': ('active', 'pending'), 'excluded': ('excluded', 'excluded_auto')}.get(f['stage'], (f['stage'],))
            sql.append(STATUS_SQL + ' IN (%s)' % ', '.join('?' * len(want))); args.extend([idle_cutoff()] + list(want))
        elif f.get('stage') == 'flagged':
            sql.append(REVIEW_SQL)
        elif f.get('stage') == 'synthetic':
            sql.append(SYN_SQL)
        elif f.get('stage') == 'real':
            sql.append('NOT ' + SYN_SQL)
        for col in ('grp', 'source', 'stage', 'cond'):
            if col == 'stage' and f.get(col) in ACTIVITY + ANALYSIS:
                continue
            if f.get(col):
                sql.append('%s = ?' % col); args.append(f[col])
        if f.get('neuro'):
            sql.append("(' ' || neuro || ' ') LIKE ?"); args.append('%% %s %%' % f['neuro'])
        if f.get('q'):
            sql.append('pid LIKE ?'); args.append('%%%s%%' % f['q'])
        ids = [x for x in re.split(r'[\s,]+', f.get('pids') or '') if x][:90]   # D1 takes at most 100 values a query
        if ids:
            sql.append('pid IN (%s)' % ', '.join('?' * len(ids))); args.extend(ids)
        if f.get('since'):
            sql.append('started >= ?'); args.append(f['since'])
        if f.get('until'):
            sql.append('started < ?'); args.append(f['until'] + 'T99')
        return (' WHERE ' + ' AND '.join(sql)) if sql else '', args

    def query(self, f, sort='started', desc=True, limit=100, offset=0, grouped=False, thumbs=False):
        """The matching sessions, sorted; grouped (the Sessions tab): the analysed ones first, then those in progress
        now, then the rest (left out, stopped, no pizza, declined; listgroup 0 / 1 / 2), each group in the chosen order.
        Returns (rows, total, finished, how many are in group 2)."""
        w, a = self.where(f)
        sort = sort if sort in SORTABLE else 'started'
        db = self.db()
        cut = idle_cutoff()
        total = db.execute("SELECT COUNT(*), SUM(stage = 'done'), SUM(" + LIST_GROUP_SQL + " = 2) FROM sessions" + w, [cut] + a).fetchone()
        pics = (", (SELECT value FROM fields WHERE fields.pid = sessions.pid AND name = 'pz_final') AS pz_final_pic, "
                "(SELECT value FROM fields WHERE fields.pid = sessions.pid AND name = 'pz_summary') AS pz_summary_pic") if thumbs else ''
        rows = db.execute('SELECT *, ' + INCL_SQL + ' AS inclusion, ' + ANALYSIS_SQL + ' AS analysis, ' + AUTO_IN_SQL + ' AS auto_in, ' + FINISHED_SQL + ' AS pz_finished, '
                          + LIST_GROUP_SQL + ' AS listgroup, ' + STATUS_SQL + ' AS status, ' + CLIENT_SQL + pics + ' FROM sessions%s ORDER BY %s%s %s, pid LIMIT ? OFFSET ?'
                          % (w, 'listgroup, ' if grouped else '', sort, 'DESC' if desc else 'ASC'), [cut, cut] + a + [limit, offset]).fetchall()
        return [dict(r) for r in rows], total[0], total[1] or 0, total[2] or 0

    def distinct(self, col, study=None):
        w, a = self.where({'study': study})
        return [r[0] for r in self.db().execute('SELECT DISTINCT %s FROM sessions%s ORDER BY 1' % (col, w), a) if r[0] != '']

    def last_started(self, study):
        """When the newest real session of a study (None = all) started."""
        w, a = self.where({'study': study})
        return self.db().execute('SELECT MAX(started) FROM sessions%s %s NOT %s' % (w, 'AND' if w else 'WHERE', SYN_SQL), a).fetchone()[0]

    def median_seconds(self, study):
        """Median time taken by the finished real sessions of a study (None = all)."""
        w, a = self.where({'study': study, 'stage': 'done'})
        v = sorted(r[0] for r in self.db().execute('SELECT seconds FROM sessions%s AND NOT %s' % (w, SYN_SQL), a) if r[0] is not None)
        return None if not v else (v[len(v) // 2] if len(v) % 2 else (v[len(v) // 2 - 1] + v[len(v) // 2]) / 2)

    def counts_by_study(self):
        """{study: {'n': real sessions, 'done': reached the thank-you page, 'syn': synthetic sessions, 'status': {status:
        count}}}: the statuses of the real sessions add up to n."""
        out = {}
        for r in self.db().execute('SELECT study, ' + STATUS_SQL + ' AS status, COUNT(*) n, SUM(stage = \'done\') done FROM sessions WHERE NOT '
                                   + SYN_SQL + ' GROUP BY study, status', (idle_cutoff(),)):
            c = out.setdefault(r['study'], {'n': 0, 'done': 0, 'syn': 0, 'status': {k: 0 for k in STATUSES}})
            c['n'] += r['n']; c['done'] += r['done'] or 0; c['status'][r['status']] = r['n']
        for r in self.db().execute('SELECT study, COUNT(*) n FROM sessions WHERE ' + SYN_SQL + ' GROUP BY study'):
            out.setdefault(r['study'], {'n': 0, 'done': 0, 'syn': 0, 'status': {k: 0 for k in STATUSES}})['syn'] = r['n']
        return out

    # ---- settings kept in the database
    def meta(self, k):
        r = self.db().execute('SELECT v FROM meta WHERE k = ?', (k,)).fetchone()
        return r['v'] if r else None

    def set_meta(self, k, v):
        with self.tx() as db:
            db.execute('INSERT OR REPLACE INTO meta VALUES (?, ?)', (k, str(v)))

    # ---- synthetic sessions of a test study
    def synthetic_count(self, study):
        return self.db().execute('SELECT COUNT(*) FROM sessions WHERE study = ? AND ' + SYN_SQL, (study,)).fetchone()[0]

    def sync_synthetic(self, study, n):
        """Makes the study hold exactly synthetic sessions SYN-001 … SYN-n (analysis/synthetic.py; the same ids always
        give the same sessions). Returns (added, removed)."""
        import synthetic                                     # analysis/ is on the path (server.py)
        if self.meta('synthetic_version:' + study) != synthetic.VERSION:   # made by another version: start again
            with self.tx() as db:
                db.execute('DELETE FROM fields WHERE pid IN (SELECT pid FROM sessions WHERE study = ? AND %s)' % SYN_SQL, (study,))
                db.execute('DELETE FROM sessions WHERE study = ? AND ' + SYN_SQL, (study,))
            self.set_meta('synthetic_version:' + study, synthetic.VERSION)
        have = {r[0] for r in self.db().execute('SELECT pid FROM sessions WHERE study = ? AND ' + SYN_SQL, (study,))}
        want = synthetic.sessions(n, study) if n else []
        keep = {x['pid'] for x in want}
        add = [x for x in want if x['pid'] not in have]
        drop = [p for p in have if p not in keep]
        with self.tx() as db:
            for x in add:
                db.execute('INSERT OR IGNORE INTO sessions (pid, study, grp, source, invite, cond, stage, started, updated, finished, seconds, restarts, consent, '
                           'n_pieces, neuro) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                           [x[c] for c in ('pid', 'study', 'grp', 'source', 'invite', 'cond', 'stage', 'started', 'updated', 'finished', 'seconds',
                                           'restarts', 'consent', 'n_pieces', 'neuro')])
                db.executemany('INSERT OR REPLACE INTO fields (pid, name, value, updated) VALUES (?, ?, ?, ?)',
                               [(x['pid'], k, v, x['updated']) for k, v in x['fields'].items()])
            for p in drop:
                db.execute('DELETE FROM fields WHERE pid = ?', (p,))
                db.execute('DELETE FROM sessions WHERE pid = ?', (p,))
        return len(add), len(drop)

    def records(self, f):
        """Every matching session as a dict with its fields (for exports and the analysis), oldest first."""
        w, a = self.where(f)
        pids = [r[0] for r in self.db().execute('SELECT pid FROM sessions%s ORDER BY started, pid' % w, a)]
        for pid in pids:
            yield self.get(pid)

    def signature(self, f):
        """(count, newest update) of the matching sessions, a researcher's inclusion choice counting as an update: the
        reports are rebuilt when this changes."""
        w, a = self.where(f)
        r = self.db().execute('SELECT COUNT(*), MAX(updated), MAX((SELECT updated FROM fields WHERE fields.pid = sessions.pid AND name = ?)) FROM sessions'
                              + w, [INCLUSION] + a).fetchone()
        # and how many sessions are excluded / included by hand: times have one-second steps, so a choice undone within
        # the same second would otherwise leave the signature (and the stale reports) as they were
        c = self.db().execute('SELECT COALESCE(SUM(v = ?), 0), COALESCE(SUM(v = ?), 0) FROM (SELECT (SELECT value FROM fields WHERE fields.pid = sessions.pid AND name = ?) AS v FROM sessions'
                              + w + ')', ['exclude', 'include', INCLUSION] + a).fetchone()
        return '%d|%s|x%d,i%d' % (r[0], max(r[1] or '', r[2] or ''), c[0], c[1])

    def set_inclusion(self, pid, value, study=None):
        """The researcher's choice for a session: 'include', 'exclude' or 'auto'. study: only a session of this study (a
        study researcher's scope). False when there is no such session."""
        with self.tx() as db:
            row = db.execute('SELECT study FROM sessions WHERE pid = ?', (pid,)).fetchone()
            if row is None or (study is not None and row['study'] != study) or value not in INCLUSION_VALUES:
                return False
            db.execute('INSERT INTO fields (pid, name, value, updated) VALUES (?, ?, ?, ?) '
                       'ON CONFLICT(pid, name) DO UPDATE SET value = excluded.value, updated = excluded.updated', (pid, INCLUSION, value, now()))
        return True

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
