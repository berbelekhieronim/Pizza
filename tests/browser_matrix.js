// The participant page under restrictive browser conditions (simulated; docs/BROWSERS.md): what the participant sees,
// and the session id, so the database can be checked afterwards. Needs Playwright with Chromium (not part of the smoke
// test, which runs on the standard library and node only):
//   python3 server/server.py --port 8775 --data /tmp/b --key k &      then      node tests/browser_matrix.js 8775
// and look at /tmp/b/study.db (fields browser_flags, translated, pz_final of the printed session ids).
// "beacons-blocked" does not reproduce an ad blocker here (Playwright does not intercept beacons); "no-sendBeacon"
// covers the same path.
const { chromium } = require('playwright');
const B = 'http://127.0.0.1:' + process.argv[2];
const post = (pid, stage) => fetch(B + '/api/save', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ pid, stage, fields: {} }) });

const CASES = {
  'normal': {},
  'cookies-blocked': { init: () => { for (const k of ['sessionStorage', 'localStorage']) Object.defineProperty(window, k, { get() { throw new DOMException('Access is denied for this document.', 'SecurityError'); } }); }, reload: true },
  'no-sendBeacon': { init: () => { delete Navigator.prototype.sendBeacon; }, leave: true },
  'beacons-blocked (uBlock)': { route: async (ctx) => ctx.route('**/api/save', (r) => (r.request().resourceType() === 'ping' ? r.abort() : r.continue())), leave: true },
  'coarse-timer (RFP)': { init: () => { const n = performance.now.bind(performance); performance.now = () => Math.floor(n() / 100) * 100; } },
  'translated': { after: async (p) => { await p.evaluate(() => { document.documentElement.classList.add('translated-ltr'); document.documentElement.lang = 'en'; }); await p.waitForTimeout(4600); } },
  'start busy (429 x2)': { route: async (ctx) => { let n = 0; await ctx.route('**/api/start*', (r) => (n++ < 2 ? r.fulfill({ status: 429, contentType: 'application/json', body: '{"error":"Too many"}' }) : r.continue())); } },
  'turnstile blocked': { route: async (ctx) => {
    let first = true;
    await ctx.route('**/api/start*', (r) => { if (first) { first = false; return r.fulfill({ contentType: 'application/json', body: '{"verify":"site-key"}' }); } r.continue(); });
    await ctx.route('https://challenges.cloudflare.com/**', (r) => r.abort());
  } },
  'turnstile blocked, server strict': { route: async (ctx) => {
    await ctx.route('**/api/start*', (r) => r.fulfill({ contentType: 'application/json', body: '{"verify":"site-key"}' }));
    await ctx.route('https://challenges.cloudflare.com/**', (r) => r.abort());
  }, noConsent: true },
  'old browser (no fetch)': { init: () => { delete window.fetch; }, noConsent: true },
  'javascript off': { js: false, noConsent: true },
};

(async () => {
  const b = await chromium.launch(), out = {};
  for (const [name, c] of Object.entries(CASES)) {
    const ctx = await b.newContext({ viewport: { width: 1440, height: 900 }, javaScriptEnabled: c.js !== false }), errs = [], startUrls = [];
    if (c.init) await ctx.addInitScript(c.init);
    if (c.route) await c.route(ctx);
    ctx.on('request', (r) => { if (r.url().includes('/api/start')) startUrls.push(new URL(r.url()).searchParams.get('nocheck') || ''); });
    let p = await ctx.newPage(); p.on('pageerror', (e) => errs.push(String(e).slice(0, 100)));
    await p.goto(B + '/?study=pilot-2026-11');
    await p.waitForTimeout(name.startsWith('start busy') ? 8000 : 1500);
    const first = ((await p.textContent('#stage')) || '').trim().replace(/\s+/g, ' ').slice(0, 90);
    const r = { first };
    if (!c.noConsent && (await p.$('#yes'))) {
      await p.click('#yes'); await p.waitForTimeout(900);
      r.url = p.url().replace(B, '');
      r.pid = new URL(p.url()).searchParams.get('pid') || (await p.evaluate(() => { try { return sessionStorage.getItem('pz-pid'); } catch (e) { return null; } }));
      if (c.reload) {             // a reload must come back to the same session
        await p.reload(); await p.waitForTimeout(1500);
        r.afterReload = ((await p.textContent('#stage')) || '').trim().slice(0, 40);
        r.notice = ((await p.textContent('#notice')) || '').trim();
      }
      if (c.leave) {              // build stage, one topping, leave 1 s later (before the 4-second batch)
        await p.goto('about:blank'); await p.waitForTimeout(500); await post(r.pid, 'build'); await p.goto(B + '/?study=pilot-2026-11&pid=' + r.pid); await p.waitForTimeout(1500);
        const piz = await p.locator('.pzb-pizza').boundingBox(), it = await p.locator('.pzb-item[data-ing="tof"]').boundingBox();
        await p.mouse.move(it.x + it.width / 2, it.y + it.height / 2); await p.mouse.down();
        for (let s = 1; s <= 10; s++) await p.mouse.move(it.x + it.width / 2 + (piz.x + piz.width / 2 - it.x - it.width / 2) * s / 10, it.y + it.height / 2 + (piz.y + piz.height / 2 - it.y - it.height / 2) * s / 10);
        await p.mouse.up(); await p.waitForTimeout(1000);
        await p.goto('about:blank'); await p.waitForTimeout(1200);
      }
      if (c.after) await c.after(p);
    }
    r.nocheck = startUrls.filter(Boolean);
    r.errors = errs;
    out[name] = r;
    await ctx.close();
  }
  console.log(JSON.stringify(out, null, 1));
  await b.close();
})();
