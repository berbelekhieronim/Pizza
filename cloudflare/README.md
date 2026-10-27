# The pizza study on Cloudflare

One web address for everything: participants open `https://pizza-study.<your-subdomain>.workers.dev/` (or your own
domain), researchers open `…/admin?key=…` at the same address. Nothing runs on your computer or in a Codespace:
Cloudflare serves the study and stores the data, and GitHub deploys it and builds the reports.

```
participant ─┐                        Cloudflare (one Worker, one address)
researcher ──┴─> pizza-study.<you>.workers.dev ──> /            the participant page + pizza-builder.js (static files)
                                                 ├> /api/...    start, save, resume       ──> D1 database (SQLite)
                                                 └> /admin...   session browser, links,   ──> D1
                                                                reports and downloads     ──> R2 storage
GitHub ── push to main ──> checks ──> .github/workflows/cloudflare.yml: deploy (Worker, database, storage, settings)
       └─ reports.yml (when a researcher presses "Build reports"; optionally after sessions finish):
          tools/cloud_sync.py: download the sessions → analysis/analyse.py per study → store reports and downloads in R2
```

- **Same study, same data.** The Worker (`src/`) does what `server/server.py` does, with the database schema of
  `server/store.py` (`migrations/0001_init.sql`). A downloaded `study.sqlite` reads exactly like the Codespace's
  `study.db`, in R or with `analyse.py`. `server/study.json` is the study's settings for both; edit it, push, and
  the site updates.
- **What differs from the Codespace server.** Reports and the R, raw and database downloads are built by GitHub per
  study (and for all studies together) and kept until the next build. The session list and its `.csv` follow every
  filter, as before. The researcher page says when the reports were built and whether newer sessions have arrived.
- **Protection against bots and abuse.**
  - A new session needs Cloudflare Turnstile's invisible check that a person opened the link. It usually passes by
    itself. Returning participants and personal links skip it.
  - Rate limits per connection: 30 new sessions a minute (a room of people on one network still fits), 120 saves a
    minute per session, 120 researcher-page requests a minute.
  - Search engines are asked to stay away (`robots.txt`, `noindex`).
  - Unknown study and personal links are refused, and saves only reach sessions that exist.
  - The researcher pages need a key (the owner's 16+ characters, or a study's random key), compared in constant
    time. Keys are not logged: request logging (observability) is off.

## Setting it up (once, about 10 minutes)

The deploy does almost everything itself: it finds your account, gives the account a `workers.dev` address if it
has none, creates the Turnstile bot check for that address, the database and the storage, and deploys. You make
one Cloudflare token and give GitHub two secrets.

1. **Cloudflare account** with **R2 enabled**: *R2 Object Storage* in the left menu, enable it. R2 asks for a card,
   but the study cannot spend on it: see *Hard caps* below.
2. **The token.**
   - Click your profile icon (top right), then **My Profile → API Tokens → Create Token**.
   - Scroll to the bottom and choose **Create Custom Token → Get started**. Name it `pizza-study`.
   - Under **Permissions** each row has three drop-downs. Fill the first row, then click **+ Add more** for each next
     one:

     | 1st drop-down | 2nd drop-down | 3rd drop-down |
     |---|---|---|
     | Account | Workers Scripts | Edit |
     | Account | D1 | Edit |
     | Account | Workers R2 Storage | Edit |
     | Account | Turnstile | Edit |
     | Account | Account Settings | Read |
     | User | User Details | Read |
     | User | Memberships | Read |

   - Under **Account Resources** choose *Include → All accounts* (or your account).
   - Click **Continue to summary → Create Token** and copy the token. It is shown once.
3. **A researcher password**: any long password (16+ characters) that you keep safe. It opens every study's data.
4. **GitHub**: open the repository's **Settings → Secrets and variables → Actions → New repository secret**, twice:

   | Name | Value |
   |---|---|
   | `CLOUDFLARE_API_TOKEN` | the token |
   | `PIZZA_ADMIN_KEY` | the password |

5. **Deploy**: **Actions → cloudflare → Run workflow → Run workflow**.
   - The run's summary lists what the token can reach. A **FAIL** line names the permission to add: edit the token
     in Cloudflare (*API Tokens → … → Edit*) and run the workflow again.
   - When it is green, the summary shows the study's address.
6. **Open** `https://<the address>/admin?key=<your password>`. *Studies and links* has the participant links and
   each study's researcher link.

Not needed: Turnstile set-up by hand (the deploy makes the widget and its hostname), the Account ID (found from the
token; add a `CLOUDFLARE_ACCOUNT_ID` secret only if the token reaches several accounts), and Zero Trust (the study
does not use it; its free plan bills nothing).

**Reports on request (the default).** The reports are built when a researcher presses **Build reports** on the
researcher page. Until then the page shows "New data · press Build reports" (a session that changed, or an
include/exclude choice on the Sessions tab, counts as new data). The build analyses only the studies whose sessions
changed, skips studies with no pizza yet, and finishes at once when nothing changed; a change to the analysis code
rebuilds everything once. Nothing runs between visits: no schedules, no polling, no build per finished session. The page
shows the build's progress (spinner, step, log, link to the run).

**Automatic reports (optional).** Set the repository variable `PIZZA_REPORTS_AUTO` to `1` and deploy again: then a
finished session queues one build, which waits until nobody has saved for 5 minutes (sessions finishing close together
share one build), and each deploy rebuilds the reports. Remove the variable (and deploy) to go back to on request.

**The token (`PIZZA_GITHUB_TOKEN`, or `PIZZA_GITHUB_TOKEN_PIZZA`).** It lets the site start the reports job when someone
presses *Build reports*. Without it, start builds from *Actions → reports → Run workflow* (tick *force* to rebuild
everything). Make the token at github.com → *Settings → Developer settings →
Fine-grained tokens*: this repository only, permission **Actions: Read and write**.

**Your own domain (optional).** Add it to Cloudflare, add a custom domain to the `pizza-study` Worker, set the
repository variable `PIZZA_SITE_URL` (e.g. `https://pizza.example.org`), and deploy again. The bot check is updated
for the new address.

## Moving sessions between studies

**Actions → move sessions → Run workflow** moves sessions and personal links from one study to another in the live
database, e.g. *from* `all` *to* `tests` to label everything collected so far as test data. The reports are rebuilt
afterwards. The target study must be in `server/study.json` (`tests` is: the team's own test runs, with the nutrition
button on).

## Where the computing happens

| where | what | how much |
|---|---|---|
| **Cloudflare Worker** (free plan) | participant pages, saving (every 4 s while someone builds), the researcher page | about 100–300 requests and 300–800 database writes per participant |
| **GitHub: reports job** (public repo: free) | downloading the sessions, the analysis, storing the reports | one run per press of *Build reports*: seconds when nothing changed, a minute or two otherwise (only changed studies are analysed); each pizza's slow measures (the symmetry search) are computed once and cached between runs |
| **GitHub: check** (on every code push) | the full smoke test on two Python versions, R, face benchmark | 2–4 minutes; skipped for documentation-only pushes |
| **GitHub: cloudflare** (on every code push) | a one-minute test of the Worker, then the deploy and a check of the live site | about a minute |
| **Your browser** | the researcher page | refreshes itself only while a build is queued or running, and not when its tab is hidden |

## Hard caps: the study never makes Cloudflare bill you

Stay on the **free plans**: do not upgrade to Workers Paid. On the free plans, Workers and D1 cannot bill: at their
daily limits requests fail until the next day. **R2 is the one product that bills by use** once a card is on file, so
the Worker enforces caps below R2's free tier itself:

| | R2 free tier | hard cap in the Worker | when reached |
|---|---|---|---|
| storage | 10 GB | **8 GB** | the reports job stops before uploading, and the Worker refuses any write that would pass it |
| writes (class A) | 1 million / month | **800,000 / month** | uploads refused until the next month |
| reads (class B) | 10 million / month | **8 million / month** | reports and downloads unavailable until the next month (the study itself keeps running) |
| database (D1) | 500 MB (free plan maximum) | **450 MB** | new participants see "not taking new participants"; people already in can finish |

- The caps can be lowered (repository variables → Worker vars `R2_LIMIT_BYTES`, `R2_WRITES_PER_MONTH`,
  `R2_READS_PER_MONTH`, `D1_LIMIT_BYTES`) but **never raised**: higher values are clamped to the caps above.
- The Worker counts every R2 operation in the database before doing it. If the counter cannot be updated, the
  operation does not happen: the caps fail closed.
- The owner's researcher page shows storage, this month's writes and reads, and the database size against the caps.
- Database copies are stored compressed (browsers unpack them on download), so the reports and downloads of a few
  thousand participants fit in a fraction of the 8 GB.
- Belt and braces (optional): Cloudflare dashboard → *Notifications → Add → Usage Based Billing*, to be emailed if
  anything ever starts to bill.

What the free plans hold, roughly (Cloudflare's limits in 2025):

| | free | what the study uses |
|---|---|---|
| Workers requests | 100,000 / day | ~1 save a second while someone builds: roughly 300–600 requests per participant, so ~150 participants a day |
| D1 rows written | 100,000 / day | only changed fields are written: roughly 1,000–2,000 per participant, so ~50–100 participants a day |
| D1 storage | 500 MB per database | ~0.1–0.5 MB per participant, so ~1,000–4,000 participants |

## Data protection

- Participant data is stored by Cloudflare: D1 placed in Eastern Europe, R2 under the EU jurisdiction. Cloudflare is a
  processor under its Data Processing Addendum, which you accept in the dashboard.
- **GitHub also handles the data.** The reports job runs on GitHub's servers, which download the sessions, analyse
  them, and delete them when the job ends. The job's log shows counts only, and nothing is kept as an artifact. The
  repository is public, so its Actions logs are too.
- If your ethics approval or data protection officer does not allow GitHub to process the data, turn off the reports
  workflow (*Actions → reports → Disable*). Build the reports on an approved computer instead, with
  `PIZZA_SITE_URL=… PIZZA_ADMIN_KEY=… python3 tools/cloud_sync.py`. It does the same as the job: standard Python, no
  installs.
- The "About you" answers are health-related data. Check retention and access against the approval, and download
  *Database (.sqlite)* regularly as a backup.

## Working on it locally

```
cd cloudflare && npm ci                       # wrangler (pinned), once
python3 deploy.py build                       # public/: the participant page and the task script
npx wrangler d1 migrations apply pizza-study --local
npx wrangler dev --var ADMIN_KEY:local-key-123   # http://localhost:8787/ and /admin?key=local-key-123
PIZZA_SITE_URL=http://localhost:8787 PIZZA_ADMIN_KEY=local-key-123 python3 ../tools/cloud_sync.py   # reports
```

`python3 tests/smoke_test.py` runs the same checks against the Worker in the local Workers runtime (section
*cloudflare*), including the reports job, the access rules and the bot protection. CI does too.
