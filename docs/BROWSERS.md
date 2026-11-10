# Browsers, privacy settings and blockers

What participants' browsers may refuse or change, what that did to the study before, and what the participant page
does about it now (study server 0.14.0). Everything here concerns `server/participate.html`, the page both study
servers serve; the task itself (`pizza-builder.js`) needs nothing a browser can switch off except JavaScript.

## What the study needs from a browser

| need | used for | can be refused by |
|---|---|---|
| JavaScript | everything | NoScript, "JavaScript off" in settings |
| `fetch` to the study's own address (`/api/start`, `/api/save`, `/study.json`) | starting and saving the session | nothing common: same address, no tracking-like names |
| `sessionStorage` | finding the session again after a reload | "Block all cookies" in Chrome, Edge or Firefox; some privacy extensions. **Even reading it throws an error then.** |
| `navigator.sendBeacon` | the last save as the page closes | Firefox `beacon.enabled = false` (hardened setups); ad blockers can block beacon requests |
| Cloudflare Turnstile (`challenges.cloudflare.com`) | the "are you a person" check before a new session (Cloudflare only) | blockers, firewalls, strict privacy modes; it can also fail in hardened browsers |
| An accurate clock (`performance.now`) | every time in the task (decisions, drags, hovers) | fingerprinting protection: Firefox "resist fingerprinting", Tor Browser (steps of 16-100 ms) |
| The page's own colours and words | the stimulus | automatic dark mode, Dark Reader, Windows high contrast, "Translate this page" |
| Many new sessions from one address | a computer lab, a university network (one shared address) | the Worker's limit: 30 new-session requests a minute per address |

## What happened before, and what happens now

Each case was run in Chromium (Playwright) against a local study server, with the condition simulated, before and
after the change: `tests/browser_matrix.js` (how to run it is at its top; rerun it when the page changes).

| condition | before | now |
|---|---|---|
| Cookies / storage blocked | **blank page**: the page stopped on the first read of `sessionStorage`; no session, no trace | runs normally; the session id goes into the address (`&pid=`), so a reload comes back to the same session; flag `storage-blocked` |
| No `sendBeacon` | the last seconds before closing (e.g. the last topping) were lost | saved: leaving or hiding the page sends the unsaved fields with `fetch(keepalive)`, the beacon is only the fallback; flag `no-beacon` |
| Beacons blocked by an ad blocker | as above (not reproducible in Playwright, but the same path) | as above |
| Tab hidden, computer asleep, Safari closing a tab without `pagehide` | saved at the next 4-second batch, if the page ran again | saved at once when the page is hidden (`visibilitychange`) |
| Too many starts from one network (HTTP 429) | "this link does not work" with an English message; the person had to reload | "connecting…" and retried for about two minutes (2, 4, 8, 15, 30, 60 s), then starts |
| No connection or server error at the start | "could not start" at once | retried as above |
| Turnstile script blocked or failing | "could not start", or the page waited on "one moment" forever | never waits: on a block, an error, "unsupported" or 45 s it asks the server again with the reason (`nocheck=`); the Worker still asks for the check, so the participant sees **"could not confirm… switch off ad blocking or privacy extensions for this page, or use another browser"** |
| Very old browser (no `fetch`) or the task script blocked | blank page | a message in Polish and English: use a current browser |
| JavaScript off | blank page | a message in Polish and English (`<noscript>`) |
| Automatic dark mode, Dark Reader | the pizza's colours could be changed | locked: `color-scheme: only light`, `<meta name="darkreader-lock">` |
| Windows high contrast | colours replaced | recorded: flag `forced-colors` |
| "Translate this page" | the participant read a machine translation; nobody knew | recorded: flag `translated`, and the session field `translated` (the part, the time, the language). Not prevented |
| Fingerprinting protection (coarse clock) | timings in steps of 16-100 ms, silently | recorded: flag `coarse-timer` (clock step ≥ 10 ms); `client.timerMs` has the step |
| A program driving the browser | not visible | recorded: flag `automated` (`navigator.webdriver`) |

## Where the flags show

- Session field `browser_flags` (space-separated, see above; `brave` marks Brave, which reports itself as Chrome and
  varies some device values), `translated`, and `client` (with `storage`, `cookies`, `beacon`, `timerMs`, `webdriver`,
  `brave`, `gpc`, `dnt`, `forcedColors`, `reducedMotion`). See `CODEBOOK.md` → *Study server session fields*.
- The Sessions tab: a ⚠ in the *Device* column (hover for what happened); the session list download (`browser_flags`,
  `translated`); `participants.csv` (`browser_flags`). Before analysing timings, look at the sessions with
  `coarse-timer`; before analysing what people read, the ones with `translated`.

## Open decision (not changed)

When Turnstile cannot run, the participant can still not take part (the message tells them what to do). Two changes
would keep these people, at the cost of weaker spam protection; they need the researchers' decision:

1. **Start the session anyway, marked** (`bot_check: unchecked: <reason>`), with a cap on such sessions across the
   site and a switch to turn it off. The page already sends the reason; only the Worker would change.
2. **Raise the limit of new sessions per address** (30 a minute, `START_LIMIT` in `cloudflare/wrangler.json`) for
   sessions run in a lab. The page's retries already cover a class starting together, more slowly.

## Not handled (by design)

- Phones and tablets: the study is desktop only; these visits start no session and leave no trace (HANDOFF).
- Browsers that hide their real values (Brave, Firefox with fingerprinting protection, Tor): `screen`, `cores`, `tz`
  (UTC) and the user agent can be made up. The flags say when this is likely.
