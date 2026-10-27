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
       └─ reports.yml (a few minutes after sessions finish, "Rebuild now", every 6 h):
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

## Setting it up (once, about 20 minutes)

1. **Cloudflare account** (free): sign up at dash.cloudflare.com.
   - Open *Workers & Pages* once and choose your `workers.dev` subdomain, e.g. `swps-pizza`. The study will be at
     `https://pizza-study.swps-pizza.workers.dev`.
   - Open *R2* once and enable it. It is free up to 10 GB, but Cloudflare asks for a payment method.
2. **API token**: *My Profile → API Tokens → Create Token*. Start from the **Edit Cloudflare Workers** template, then
   *+ Add more*: **Account → D1 → Edit**. Limit it to your account and create it.
   - Copy the token.
   - Copy your **Account ID**, shown on the right of the *Workers & Pages* overview.
3. **Turnstile (bot check)**: *Turnstile → Add widget*.
   - Name it `pizza-study`.
   - Add the hostname `pizza-study.<subdomain>.workers.dev`.
   - Widget mode: *Managed* (invisible for most people).
   - Copy the **site key** and the **secret key**.
4. **Researcher password**: make one, for example with
   `python3 -c "import secrets; print(secrets.token_urlsafe(18))"`. Keep it safe: it opens every study's data.
5. **GitHub**: in the repository, go to *Settings → Secrets and variables → Actions*.
   - *Secrets*:

     | secret | value |
     |---|---|
     | `CLOUDFLARE_API_TOKEN` | the token from step 2 |
     | `CLOUDFLARE_ACCOUNT_ID` | the Account ID |
     | `PIZZA_ADMIN_KEY` | the password from step 4 |
     | `PIZZA_TURNSTILE_SECRET` | Turnstile's secret key |
     | `PIZZA_GITHUB_TOKEN` | optional, see below |

   - *Variables*: `PIZZA_TURNSTILE_SITE_KEY` = Turnstile's site key. `PIZZA_SITE_URL` is needed only with your own
     domain.
6. **Deploy**: *Actions → cloudflare → Run workflow*. It deploys again after every push to `main` that passes the
   checks. The first run creates the database (placed in Eastern Europe) and the storage (EU jurisdiction). The run's
   summary shows the address.
7. **Open** `https://pizza-study.<subdomain>.workers.dev/admin?key=<your password>`. *Studies and links* has the
   participant links and each study's researcher link.

**Rebuild on request (`PIZZA_GITHUB_TOKEN`, optional).** With it, the site starts the reports job a few minutes after
sessions finish and when someone presses *Rebuild now*. Without it, reports are rebuilt every 6 hours, after each
deploy, and from *Actions → reports → Run workflow*. Make the token at github.com → *Settings → Developer settings →
Fine-grained tokens*: this repository only, permission **Actions: Read and write**.

**Your own domain (optional).** Add it to Cloudflare, add a custom domain to the `pizza-study` Worker, set the
`PIZZA_SITE_URL` variable (e.g. `https://pizza.example.org`), add the hostname to the Turnstile widget, and redeploy.

## Costs and limits

The free plans cover a pilot. These are Cloudflare's limits in 2025; check their pricing pages.

| | free | what the study uses |
|---|---|---|
| Workers requests | 100,000 / day | ~1 save a second while someone builds: roughly 300–600 requests per participant, so ~150 participants a day |
| D1 rows written | 100,000 / day | only changed fields are written: roughly 1,000–2,000 per participant, so ~50–100 participants a day |
| D1 storage | 5 GB | ~0.1–0.5 MB per participant |
| Worker CPU | 10 ms / request | the researcher page with very many sessions may need more |
| R2 | 10 GB, 1M writes / month | reports: a few MB per build |

For a larger study, the **Workers Paid** plan ($5 a month) raises these limits: 10 million requests and 50 million
D1 rows written a month, and 30 s of CPU per request.

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
