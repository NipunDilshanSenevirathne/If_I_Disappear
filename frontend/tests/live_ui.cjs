/* The screens a real family uses on a hosted copy with a key, tested against a server in live
   mode whose key is not real, whose model addresses go nowhere and whose daily budget is $0, so
   nothing can be spent:

     cd backend && MODEL_API_KEY=not-a-real-key IID_MODE=live IID_ADMIN_TOKEN=ui-test-invite \
       IID_MAX_UPLOAD_MB=1 IID_UPLOAD_CHUNK_KB=256 IID_DAILY_BUDGET_USD=0 META_BASE_URL=http://127.0.0.1:9/v1 \
       VOICE_TRANSCRIBE_URL=http://127.0.0.1:9/asr uvicorn app.main:app --port 8086
     BASE=http://127.0.0.1:8086 INVITE=ui-test-invite node frontend/tests/live_ui.cjs

   It starts a home from the Start page (with a wrong invite code first), opens Record, refuses
   a video over the server's limit before sending anything, sends a small real video in pieces
   over a slow connection, and follows the walk-through until it stops at the spending cap: the
   video arrived whole and was converted, and the stop is explained. A file that isn't a video is
   refused with a reason, and a blocked microphone is said so on the help page. Needs ffmpeg. */
const { chromium } = require('playwright');
const { execFileSync } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

const BASE = process.env.BASE || 'http://127.0.0.1:8086';
const INVITE = process.env.INVITE || 'ui-test-invite';
const SHOTS = process.env.SHOTS || ''; // a folder for screenshots of the Start page and Record, for the docs
const AXE = fs.readFileSync(require.resolve('axe-core/axe.min.js', { paths: [path.join(__dirname, '..')] }), 'utf8');

let failed = 0;
function check(name, ok, detail = '') {
  if (!ok) failed += 1;
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? `  (${detail})` : ''}`);
}

async function axe(page, name) {
  await page.evaluate(AXE);
  const res = await page.evaluate(async () => {
    // eslint-disable-next-line no-undef
    const r = await axe.run(document, { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa'] } });
    return r.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical').map((v) => `${v.id} x${v.nodes.length}`);
  });
  check(`axe ${name}: no serious or critical issues`, res.length === 0, res.join('; '));
}

(async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'iid-live-ui-'));
  const small = path.join(tmp, 'walk.mp4');
  const big = path.join(tmp, 'too-big.mp4');
  const notVideo = path.join(tmp, 'notes.mp4');
  fs.writeFileSync(notVideo, 'These are my notes about the house, not a video.\n'.repeat(40));
  // Four seconds of picture and sound, with noise so it doesn't compress away: about 800 KB,
  // four pieces of 256 KB, under the test server's 1 MB limit.
  execFileSync('ffmpeg', ['-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc=size=640x360:rate=30', '-f', 'lavfi', '-i', 'sine=frequency=440', '-t', '4', '-vf', 'noise=alls=30:allf=t', '-c:v', 'libx264', '-b:v', '1400k', '-maxrate', '1400k', '-bufsize', '2800k', '-c:a', 'aac', '-shortest', small]);
  fs.writeFileSync(big, Buffer.alloc(Math.round(1.5 * 1024 * 1024), 7));

  const health = await (await fetch(`${BASE}/api/health`)).json();
  check('server: live, invite-only, 1 MB limit for this test', health.mode === 'live' && health.invite_only === true && health.max_upload_mb === 1, JSON.stringify({ mode: health.mode, invite_only: health.invite_only, max: health.max_upload_mb }));

  const browser = await chromium.launch();
  // The guided tour opens on a first visit; these checks start as a visitor who has closed it.
  const newContext = browser.newContext.bind(browser);
  browser.newContext = async (opts = {}) => {
    const c = await newContext(opts);
    await c.addInitScript(() => {
      try {
        if (!localStorage.getItem('iid.tour.v1')) localStorage.setItem('iid.tour.v1', JSON.stringify({ status: 'skipped', step: 0 }));
      } catch (e) {}
    });
    return c;
  };
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, reducedMotion: 'reduce' });
  await ctx.addInitScript(() => {
    try {
      if (!localStorage.getItem('iid.lang')) localStorage.setItem('iid.lang', 'en');
    } catch (e) {}
  });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(`pageerror: ${e}`));
  const pieces = [];
  page.on('request', (r) => r.method() === 'PUT' && r.url().includes('/uploads/') && pieces.push(r.url()));

  // The landing page offers a real home only on a live server.
  await page.goto(`${BASE}/`, { waitUntil: 'networkidle' });
  check('landing: offers to start your own home', (await page.locator('a[href="/start"]').count()) >= 1);
  await page.locator('a.l-start-link').click();
  await page.waitForSelector('form.start-form');
  await axe(page, 'start');

  // A wrong invite code is refused, the right one starts the home.
  await page.fill('form.start-form input >> nth=0', 'Test home');
  await page.fill('form.start-form input >> nth=1', 'Amali');
  const inviteBox = page.locator('form.start-form input[autocomplete="off"]');
  if (SHOTS) {
    fs.mkdirSync(SHOTS, { recursive: true });
    await inviteBox.fill(INVITE);
    await page.screenshot({ path: path.join(SHOTS, 'start.png') });
  }
  await inviteBox.fill('not-the-code');
  await page.locator('form.start-form button[type=submit]').click();
  await page.waitForSelector('form.start-form .error-text');
  check('start: a wrong invite code is refused', (await page.locator('form.start-form .error-text').innerText()).includes('invite code isn’t right'));
  await inviteBox.fill(INVITE);
  await page.locator('form.start-form button[type=submit]').click();
  await page.waitForSelector('.owner-link');
  const ownerLink = await page.locator('.owner-link').innerText();
  check('start: the home is ready, with its private link', ownerLink.startsWith(`${new URL(BASE).origin}/l/`), ownerLink.slice(0, 40));

  // Record: a video over the server's limit is refused before anything is sent.
  await page.locator('a', { hasText: 'Record the first walk-through' }).click();
  await page.waitForSelector('.record-form');
  const hid = new URL(page.url()).pathname.split('/')[2];
  await page.setInputFiles('.record-form input[type=file]:not([capture])', big);
  await page.waitForSelector('.record-preview .warn-note');
  check('record: a video over the limit is explained', (await page.locator('.record-preview .warn-note').innerText()).includes('takes up to 1 MB'));
  if (SHOTS) {
    await page.locator('.record-preview .warn-note').scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(SHOTS, 'record-too-big.png') });
  }
  await page.locator('.record-form input[type=checkbox]').check();
  check('record: and it can’t be sent', await page.locator('.record-form .btn-dark').isDisabled());
  check('record: nothing was sent', pieces.length === 0);

  // A small real video goes up in pieces over a slow connection, is converted, and stops at the
  // spending cap ($0 on this server) before the first model call, which is explained.
  await page.locator('.record-preview button', { hasText: 'Choose another' }).click();
  await page.setInputFiles('.record-form input[type=file]:not([capture])', small);
  const cdp = await ctx.newCDPSession(page);
  await cdp.send('Network.enable');
  await cdp.send('Network.emulateNetworkConditions', { offline: false, latency: 150, downloadThroughput: 400 * 1024, uploadThroughput: 120 * 1024 });
  const seen = new Set();
  const watch = setInterval(async () => {
    try {
      const text = await page.locator('.record-form .btn-dark').innerText();
      const m = /(\d+)%/.exec(text);
      if (m) seen.add(Number(m[1]));
    } catch (e) {}
  }, 150);
  await page.locator('.record-form .btn-dark').click();
  await page.waitForSelector('.pipeline .error-text, .card .error-text', { timeout: 180000 }).catch(() => {});
  clearInterval(watch);
  await cdp.send('Network.emulateNetworkConditions', { offline: false, latency: 0, downloadThroughput: -1, uploadThroughput: -1 });
  check('record: the video went up in pieces', new Set(pieces.map((u) => new URL(u).searchParams.get('offset'))).size >= 3, `${pieces.length} pieces`);
  check('record: on a slow connection, the progress is shown as it goes', [...seen].some((n) => n > 5 && n < 95), [...seen].sort((a, b) => a - b).join(','));
  check('record: it was converted before the first model call', (await page.locator('.pipeline-step.pipeline-done').count()) >= 1);
  const failure = (await page.locator('.card .error-text').count()) ? await page.locator('.card .error-text').innerText() : '';
  check('record: stopping at the spending cap is explained, not hidden', failure.startsWith('It didn’t work') && failure.includes('budget is used up'), failure.slice(0, 100));

  // A file that isn't a video is refused with a reason, and nothing of it is kept.
  await page.goto(`${BASE}/h/${hid}/record`, { waitUntil: 'networkidle' });
  await page.setInputFiles('.record-form input[type=file]:not([capture])', notVideo);
  await page.locator('.record-form input[type=checkbox]').check();
  await page.locator('.record-form .btn-dark').click();
  await page.waitForSelector('.card .error-text', { timeout: 120000 }).catch(() => {});
  const bad = (await page.locator('.card .error-text').count()) ? await page.locator('.card .error-text').innerText() : '';
  check('record: a file that isn’t a video is refused with a reason', /couldn.t be read as a video/.test(bad), bad.slice(0, 100));

  // A blocked microphone is said so, with what to do instead.
  await page.goto(`${BASE}/h/${hid}/help`, { waitUntil: 'networkidle' });
  await page.locator('form.ask button', { hasText: 'Ask by voice' }).click();
  await page.waitForSelector('.error-text', { timeout: 10000 }).catch(() => {});
  check('help: a blocked microphone is explained', ((await page.locator('.error-text').count()) ? await page.locator('.error-text').innerText() : '').includes('microphone is blocked'));
  // A typed question with a PIN in it: kept with the PIN hidden (the server log is checked after the run).
  await page.fill('#ask', 'My ATM PIN is 4321, where is the bank card?');
  await page.locator('form.ask button[type=submit]').click();
  await page.waitForSelector('.answer', { timeout: 30000 }).catch(() => {});
  check('help: answered even with no jobs and no model', (await page.locator('.answer').count()) === 1);
  const shownQ = (await page.locator('.asked-q').count()) ? await page.locator('.asked-q').innerText() : '';
  check('help: the question is shown back as it was kept, with the PIN hidden', shownQ.includes('[hidden]') && !shownQ.includes('4321'), shownQ);

  // The new home's board, with nothing recorded yet.
  await page.goto(`${BASE}/h/${hid}`, { waitUntil: 'networkidle' });
  check('board: a new home says nothing is recorded yet', (await page.locator('.board-hero').innerText()).includes('Nothing recorded yet'));
  check('no script errors', errors.length === 0, errors.slice(0, 3).join(' | '));

  const token = await page.evaluate((id) => JSON.parse(localStorage.getItem('iid.tokens'))[id], hid);
  await fetch(`${BASE}/api/h/${hid}`, { method: 'DELETE', headers: { Authorization: `Bearer ${token}` } });
  await browser.close();
  fs.rmSync(tmp, { recursive: true, force: true });
  console.log(failed ? `\n${failed} failed` : '\nall passed');
  process.exit(failed ? 1 : 0);
})().catch((err) => {
  console.error(err);
  process.exit(2);
});
