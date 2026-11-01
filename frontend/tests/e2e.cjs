/* End-to-end tests for the web app against a running server (judge mode, sample home).

     node frontend/tests/e2e.cjs                 # BASE defaults to http://127.0.0.1:8080
     BASE=http://127.0.0.1:8080 SHOTS=/tmp/shots node frontend/tests/e2e.cjs
     BASE=https://<you>-if-i-disappear.hf.space NODE_USE_ENV_PROXY=1 node frontend/tests/e2e.cjs

   A server with a model key (a hosted copy) runs the same checks on the sample home, except that
   its landing and Start pages offer a real home, behind the invite code.

   Uses the Playwright that ships with the environment (require('playwright')).
   Exits non-zero on the first failed check, after printing every result so far. */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const { startRelay, reachable } = require('./relay.cjs');

const BASE = process.env.BASE || 'http://127.0.0.1:8080';
const SHOTS = process.env.SHOTS || '';
const AXE = fs.readFileSync(require.resolve('axe-core/axe.min.js', { paths: [path.join(__dirname, '..')] }), 'utf8');

const results = [];
let failed = 0;
function check(name, ok, detail = '') {
  results.push({ name, ok, detail });
  if (!ok) failed += 1;
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? `  (${detail})` : ''}`);
}

async function shot(page, name) {
  if (!SHOTS) return;
  fs.mkdirSync(SHOTS, { recursive: true });
  await page.screenshot({ path: path.join(SHOTS, `${name}.png`), fullPage: true });
}

async function axe(page, name) {
  // Evaluated through the browser's devtools protocol, so the app's strict CSP stays on.
  await page.evaluate(AXE);
  const res = await page.evaluate(async () => {
    // eslint-disable-next-line no-undef
    const r = await axe.run(document, { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa'] } });
    return r.violations.map((v) => ({ id: v.id, impact: v.impact, nodes: v.nodes.length, target: v.nodes.slice(0, 2).map((n) => n.target.join(' ')) }));
  });
  const serious = res.filter((v) => v.impact === 'serious' || v.impact === 'critical');
  check(`axe ${name}: no serious or critical issues`, serious.length === 0, serious.map((v) => `${v.id} x${v.nodes} ${v.target.join(' | ')}`).join('; '));
  return res;
}

async function noOverflow(page, name) {
  const over = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  check(`${name}: no sideways scrolling`, over <= 1, `${over}px`);
}

(async () => {
  const browser = await chromium.launch();
  // The guided tour opens on a first visit. Every check below except the tour's own starts as a
  // visitor who has already closed it; the tour's checks ask for a first visit ({ tour: true }).
  const newContext = browser.newContext.bind(browser);
  browser.newContext = async (opts = {}) => {
    const { tour, ...rest } = opts;
    const c = await newContext(rest);
    if (!tour)
      await c.addInitScript(() => {
        try {
          if (!localStorage.getItem('iid.tour.v1')) localStorage.setItem('iid.tour.v1', JSON.stringify({ status: 'skipped', step: 0 }));
        } catch (e) {}
      });
    return c;
  };
  const ctx = await browser.newContext({ viewport: { width: 375, height: 812 }, reducedMotion: 'reduce' });
  await ctx.addInitScript(() => {
    try {
      if (!localStorage.getItem('iid.lang')) localStorage.setItem('iid.lang', 'en');
    } catch (e) {}
  });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(`pageerror: ${e}`));
  page.on('console', (m) => {
    if (m.type() === 'error' && !/Failed to load resource: the server responded with a status of (401|404|410)/.test(m.text())) errors.push(`console: ${m.text()}`);
  });

  const health = await (await fetch(`${BASE}/api/health`)).json();
  const LIVE = health.mode === 'live';

  // 1. Landing
  await page.goto(`${BASE}/`, { waitUntil: 'networkidle' });
  check('landing: headline shows', (await page.locator('h1').innerText()).includes('what you know stays home'));
  check('landing: three pinned objects', (await page.locator('.pin-card').count()) === 3);
  check('landing: try button links to the sample', (await page.locator('a[href="/try"]').count()) >= 2);
  await noOverflow(page, 'landing 375px');
  await axe(page, 'landing');
  await shot(page, '01-landing');
  if (LIVE) {
    check('landing: a server with a key offers a real home too', (await page.locator('a[href="/start"]').count()) >= 1);
  } else {
    check('landing: no real-home link on a sample-only server', (await page.locator('a[href="/start"]').count()) === 0);
  }

  // 1b. Starting a real home needs a key on the server (frontend/tests/live_ui.cjs tests the rest)
  await page.goto(`${BASE}/start`, { waitUntil: 'networkidle' });
  if (LIVE) {
    await page.waitForSelector('form');
    check('start: a server with a key asks for the invite code', !health.invite_only || (await page.locator('#invite-hint').count()) === 1);
    check('start: and asks for the name of the home and who is leaving', (await page.locator('form input').count()) >= 3);
  } else {
    await page.waitForSelector('.start-judge');
    check('start: a sample-only server says a real home needs a key', (await page.locator('.start-judge').innerText()).includes('Meta Model API key'));
    check('start: and offers the sample home instead', (await page.locator('.public-main a[href="/try"]').count()) === 1);
  }

  // 2. Sample home
  await page.goto(`${BASE}/try`);
  await page.waitForURL(/\/h\/demo-/, { timeout: 15000 });
  await page.waitForSelector('.board-hero');
  const hid = page.url().split('/h/')[1].split(/[/?#]/)[0];
  check('sample: private copy created', hid.startsWith('demo-'), hid);
  check('board: headline 4 of 6', (await page.locator('.board-hero-stat').innerText()).includes('4 of 6'));
  check('board: six jobs listed', (await page.locator('.job-card').count()) === 6);
  check('board: gap questions shown', (await page.locator('.gap').count()) === 2);
  check('board: the whole two-year absence is simulated, to the day she is back', (await page.locator('.timeline-horizon').innerText()).includes('2028'));
  check('board: a long absence is drawn a month to a bar', (await page.locator('.timeline-months .timeline-week').count()) === 25);
  check('board: and its heading says month by month', (await page.locator('#timeline-title').innerText()).includes('month by month'));
  await noOverflow(page, 'board 375px');
  await axe(page, 'board');
  await shot(page, '02-board');

  // 3. A job, its clip and steps
  await page.locator('.job-card', { hasText: 'Main switch box' }).click();
  await page.waitForSelector('.task-head h1');
  check('task: title', (await page.locator('.task-head h1').innerText()) === 'Main switch box');
  await page.waitForSelector('.clip-stage');
  check('task: clip or still with outline', (await page.locator('.clip-stage video, .clip-stage img').count()) === 1 && (await page.locator('.clip-stage .mask-svg').count()) >= 0);
  check('task: two numbered steps', (await page.locator('ol.steps > li').count()) === 2);
  check('task: the owner’s Sinhala words shown under the English', (await page.locator('.item-quote[lang="si"]').count()) >= 2);
  check('task: Kasun proven', (await page.locator('.who-can li.is-proven', { hasText: 'Kasun' }).count()) === 1);
  await axe(page, 'task');
  await shot(page, '03-task');

  // 4. Prove: Nethum and the water pump, show then tell
  await page.goto(`${BASE}/h/${hid}/prove?person=p-nethum&task=water_pump`, { waitUntil: 'networkidle' });
  await page.locator('.sample-photo', { hasText: 'A different one' }).click();
  await page.waitForSelector('.verdict');
  // No pump in the photo at all: it doesn't pass, and the app says it couldn't tell rather than guess.
  check('show me: a photo with no pump in it does not pass, and says it couldn’t tell', (await page.locator('.verdict.verdict-fail').count()) === 1 && (await page.locator('.verdict').first().innerText()).includes('Couldn’t tell'));
  await page.locator('.sample-photo', { hasText: 'The right one' }).click();
  await page.waitForSelector('.verdict-pass');
  check('show me: the right pump passes', (await page.locator('.proof-card').first().locator('.verdict').innerText()).includes('Passed'));
  check('show me: SAM outline drawn on the photo', (await page.locator('.proof-photo .mask-svg path.mask-line').count()) === 1);
  await page.locator('.sample-answer', { hasText: 'I switch the pump on' }).click();
  await page.waitForFunction(() => document.querySelectorAll('.proof-card')[1]?.querySelector('.verdict'));
  check('tell me: missing the safety step fails', (await page.locator('.proof-card').nth(1).locator('.verdict').innerText()).includes('Not yet'));
  await page.locator('.sample-answer', { hasText: 'grinding noise' }).click();
  await page.waitForSelector('.celebrate', { timeout: 10000 });
  check('tell me: full answer passes and the job turns green', (await page.locator('.celebrate').innerText()).includes('Water pump'));
  await axe(page, 'prove');
  await shot(page, '04-prove');
  await page.goto(`${BASE}/h/${hid}`, { waitUntil: 'networkidle' });
  check('board: headline now 3 of 6', (await page.locator('.board-hero-stat').innerText()).includes('3 of 6'));

  // 5. Help
  await page.goto(`${BASE}/h/${hid}/help`, { waitUntil: 'networkidle' });
  await page.fill('#ask', 'The pump is making a grinding noise');
  await page.locator('form.ask button[type=submit]').click();
  await page.waitForSelector('.answer h2');
  check('help: grinding pump finds the water pump', (await page.locator('.answer h2').innerText()) === 'Water pump');
  check('help: says who chose the answer', (await page.locator('.decided-by').innerText()).includes('Chosen by'));
  await page.fill('#ask', 'I can smell gas in the kitchen');
  await page.locator('form.ask button[type=submit]').click();
  await page.waitForSelector('.answer-emergency');
  check('help: gas smell is treated as an emergency', (await page.locator('.answer-emergency').innerText()).includes('110'));
  await page.fill('#ask', 'How do I fix the washing machine?');
  await page.locator('form.ask button[type=submit]').click();
  await page.waitForSelector('.answer-none');
  check('help: unrecorded things are not guessed', (await page.locator('.answer-none h2').innerText()).includes('didn’t record'));
  await page.fill('#ask', 'How many pills does Seetha Amma take at night?');
  await page.locator('form.ask button[type=submit]').click();
  await page.waitForSelector('.answer-medical');
  check('help: a medicine question is answered by code, with who can help', (await page.locator('.answer-medical').innerText()).includes('1990'));
  await page.locator('.wa-hints .chip-btn').first().click();
  await page.waitForSelector('.wa-them:not(.wa-typing)');
  check('whatsapp preview: reply with the recorded steps', (await page.locator('.wa-them:not(.wa-typing)').first().innerText()).includes('Main switch box'));
  await axe(page, 'help');
  await shot(page, '05-help');

  // 6. Review
  await page.goto(`${BASE}/h/${hid}/review`, { waitUntil: 'networkidle' });
  check('review: two facts wait for the owner', (await page.locator('.claim').count()) === 2);
  check('review: their witnesses are listed', (await page.locator('.claim .witness').count()) >= 5);
  check('review: the flagged one says why (SAM 3.1 and Muse Spark disagreed)', (await page.locator('.claim.claim-needs_review .claim-why').innerText()).includes('pointed somewhere else'));
  await page.locator('.claim.claim-verified button', { hasText: 'Accept' }).click();
  await page.waitForSelector('.claim.claim-accepted');
  check('review: accepting it works', (await page.locator('.claim.claim-accepted').count()) === 1);
  await axe(page, 'review');
  await page.locator('.tabs button', { hasText: 'Not used' }).click();
  check('review: the medicine sentence is shown as not used', (await page.locator('.left-out-medical').innerText()).includes('medicine'));
  check('review: code says why: medical', (await page.locator('.left-out-medical .left-out-why').innerText()).includes('never turns medicine'));
  await axe(page, 'review not used');
  await page.locator('.tabs button', { hasText: 'All' }).click();
  check('review: all facts listed', (await page.locator('.claim').count()) === 21);

  // 7. Answer a gap
  await page.goto(`${BASE}/h/${hid}`, { waitUntil: 'networkidle' });
  const gap = page.locator('.gap', { hasText: 'Gas cylinder' });
  await gap.locator('button', { hasText: 'Answer' }).click();
  await gap.locator('textarea').fill('Nimal from the junction gas shop brings the new cylinder and fits it for us.');
  await gap.locator('button[type=submit]').click();
  await page.waitForFunction(() => document.querySelectorAll('.gap').length === 1);
  check('gap: answered question disappears', (await page.locator('.gap').count()) === 1);
  await page.goto(`${BASE}/h/${hid}/task/gas_cylinder`, { waitUntil: 'networkidle' });
  check('gap: typed answer shown as the owner’s note', (await page.locator('.detail-notes').innerText()).includes('Nimal'));

  // 8. Card, stickers, links
  await page.goto(`${BASE}/h/${hid}/card`, { waitUntil: 'networkidle' });
  check('card: a QR code for each job', (await page.locator('.fridge svg.qr').count()) === 6);
  await page.locator('.tabs button', { hasText: 'Stickers' }).click();
  await page.waitForSelector('.sticker');
  check('stickers: six stickers', (await page.locator('.sticker').count()) === 6);
  await page.locator('.tabs button', { hasText: 'Private links' }).click();
  await page.waitForSelector('.link-item');
  check('links: one per person staying', (await page.locator('.link-item').count()) === 3);
  await axe(page, 'card');
  await shot(page, '06-card');

  // 9. Evidence
  await page.goto(`${BASE}/h/${hid}/evidence`, { waitUntil: 'networkidle' });
  check('evidence: chain intact', (await page.locator('.chain').innerText()).includes('intact'));
  await axe(page, 'evidence');

  // 10. People
  await page.goto(`${BASE}/h/${hid}/people`, { waitUntil: 'networkidle' });
  await page.locator('button', { hasText: 'Add a person' }).click();
  await page.locator('.person-add input').first().fill('Ruwan');
  await page.locator('.person-add button[type=submit]').click();
  await page.waitForSelector('.person-row:has-text("Ruwan")');
  check('people: a new person is added', (await page.locator('.person-row', { hasText: 'Ruwan' }).count()) === 1);
  await axe(page, 'people');

  // 11. Sinhala
  await page.goto(`${BASE}/h/${hid}`, { waitUntil: 'networkidle' });
  await page.locator('.topbar .lang-toggle button[lang="si"]').click();
  await page.waitForTimeout(200);
  check('sinhala: board in Sinhala', (await page.locator('.board-hero-title').innerText()).includes('හෙට ගියොත්'));
  check('sinhala: html lang switches', (await page.evaluate(() => document.documentElement.lang)) === 'si');
  await noOverflow(page, 'board in Sinhala 375px');
  await axe(page, 'board in Sinhala');
  await shot(page, '07-board-si');
  await page.locator('.topbar .lang-toggle button[lang="en"]').click();

  // 12. Sticker and person links
  const token = await page.evaluate((id) => JSON.parse(localStorage.getItem('iid.tokens'))[id], hid);
  const links = await (await fetch(`${BASE}/api/h/${hid}/links`, { headers: { Authorization: `Bearer ${token}` } })).json();
  const sticker = links.stickers.find((s) => s.task_key === 'main_switch');
  const sticky = await browser.newContext({ viewport: { width: 375, height: 812 }, reducedMotion: 'reduce' });
  const sp = await sticky.newPage();
  await sp.goto(`${BASE}${new URL(sticker.url).pathname}`, { waitUntil: 'networkidle' });
  await sp.waitForSelector('.sticker-main h1');
  check('sticker: opens its job without signing in', (await sp.locator('.sticker-main h1').innerText()) === 'Main switch box');
  check('sticker: emergency numbers shown', (await sp.locator('.emergency-call').count()) === 3);
  await sp.waitForSelector('.sticker-main figure.clip', { timeout: 10000 }).catch(() => {});
  check('sticker: shows its own clip', (await sp.locator('.sticker-main figure.clip').count()) === 1);
  const denied = await fetch(`${BASE}/api/h/${hid}/board`, { headers: { Authorization: `Bearer ${sticker.token}` } });
  check('sticker: cannot open the whole home', denied.status === 403, String(denied.status));
  await axe(sp, 'sticker');
  await shot(sp, '08-sticker');
  const person = links.people.find((p) => p.name === 'Nethum');
  await sp.goto(`${BASE}${new URL(person.url).pathname}`, { waitUntil: 'networkidle' });
  await sp.waitForSelector('.board-hero');
  check('person link: opens the home', (await sp.locator('.board-hero').count()) === 1);
  check('person link: no recording tab for family', (await sp.locator('.bottomnav-item', { hasText: 'Record' }).count()) === 0);
  await sp.locator('.topbar .menu > button').click();
  check('person link: the full log is not on the family’s menu', (await sp.locator('.menu-panel button', { hasText: 'How we know' }).count()) === 0);
  const famLog = await fetch(`${BASE}/api/h/${hid}/evidence`, { headers: { Authorization: `Bearer ${person.token}` } });
  check('person link: the log is refused to family links', famLog.status === 403, String(famLog.status));
  const famWhole = await fetch(`${BASE}/api/h/${hid}/media/rec-walk-si/video.mp4`, { headers: { Authorization: `Bearer ${person.token}` } });
  check('person link: the whole walk-through is not for family links', famWhole.status === 403, String(famWhole.status));
  await sticky.close();

  // 12b. A sticker scanned on a phone that has never opened the home plays its own clip, for real.
  const fresh = await browser.newContext({ viewport: { width: 375, height: 812 }, reducedMotion: 'reduce' });
  const fp = await fresh.newPage();
  fp.on('pageerror', (e) => errors.push(`pageerror, fresh sticker: ${e}`));
  await fp.goto(`${BASE}${new URL(sticker.url).pathname}`, { waitUntil: 'networkidle' });
  await fp.waitForSelector('.sticker-main video', { timeout: 15000 }).catch(() => {});
  const sources = await fp.locator('.sticker-main video source').evaluateAll((els) => els.map((e) => e.getAttribute('src') || ''));
  check('sticker: its clip is the job’s own cut, not the whole walk-through', sources.length === 2 && sources.every((x) => x.includes('/jobs/main_switch-')), sources.map((x) => x.split('/').pop().split('?')[0]).join(' '));
  await fp.locator('.sticker-main .clip-play').click().catch(() => {});
  await fp
    .waitForFunction(() => {
      const v = document.querySelector('.sticker-main video');
      return !!v && v.readyState >= 2 && v.currentTime > 1.5;
    }, null, { timeout: 20000 })
    .catch(() => {});
  const played = await fp.evaluate(() => {
    const v = document.querySelector('.sticker-main video');
    return v ? { t: Math.round(v.currentTime * 10) / 10, ready: v.readyState, error: v.error ? v.error.code : null, src: (v.currentSrc.split('/').pop() || '').split('?')[0] } : null;
  });
  check('sticker: the clip really plays, with no owner on the phone', !!played && played.t >= 1.5 && played.ready >= 2 && played.error === null, JSON.stringify(played));
  check('sticker: SAM 3.1’s outline is drawn while it plays', (await fp.locator('.sticker-main .clip-stage .mask-svg').count()) >= 1);
  await shot(fp, '08b-sticker-playing');
  await fresh.close();

  // 12c. When the owner changes things: a step reworded, a person removed, every link replaced.
  const rctx = await browser.newContext({ viewport: { width: 375, height: 812 }, reducedMotion: 'reduce' });
  await rctx.addInitScript(() => {
    try {
      if (!localStorage.getItem('iid.lang')) localStorage.setItem('iid.lang', 'en');
    } catch (e) {}
  });
  const rp = await rctx.newPage();
  rp.on('pageerror', (e) => errors.push(`pageerror, second home: ${e}`));
  await rp.goto(`${BASE}/try`);
  await rp.waitForURL(/\/h\/demo-/, { timeout: 15000 });
  await rp.waitForSelector('.board-hero');
  const rhid = new URL(rp.url()).pathname.split('/')[2];
  const rtoken = await rp.evaluate((id) => JSON.parse(localStorage.getItem('iid.tokens'))[id], rhid);
  const rlinks = await (await fetch(`${BASE}/api/h/${rhid}/links`, { headers: { Authorization: `Bearer ${rtoken}` } })).json();
  await rp.goto(`${BASE}/h/${rhid}/review?show=all`, { waitUntil: 'networkidle' });
  const stepCard = rp.locator('.claim', { hasText: 'push it up' }).first();
  await stepCard.locator('button', { hasText: 'Edit wording' }).click();
  await stepCard.locator('textarea[lang="en"]').fill('Switch off the water pump first, then push the dropped switch up.');
  await stepCard.locator('button', { hasText: 'Accept' }).click();
  await rp.waitForSelector('.claim .chip-lamp', { timeout: 10000 }).catch(() => {});
  check('edit: the fact is marked as the owner’s own words', (await rp.locator('.claim', { hasText: 'Switch off the water pump first' }).locator('.chip-lamp').count()) === 1);
  await rp.goto(`${BASE}/h/${rhid}/task/main_switch`, { waitUntil: 'networkidle' });
  check('edit: Kasun, who proved the old steps, is asked to explain the new ones', (await rp.locator('.who-can li', { hasText: 'Kasun' }).innerText()).includes('steps changed'));
  check('edit: the job no longer counts as covered', !(await rp.locator('.task-head .job-chips').innerText()).includes('Someone can do it'));
  await shot(rp, '10-edited-step');

  // The owner sees each fact as the family will read it in the other language, and can fix just
  // the translation: her own language, left as it was, is kept (found in the live run on
  // 1 November, where a Sinhala translation had a misspelt word).
  await rp.goto(`${BASE}/h/${rhid}/review?show=all`, { waitUntil: 'networkidle' });
  const billCard = rp.locator('.claim', { hasText: 'Pay the electricity bill at the post office.' }).first();
  check('review: a fact shows its Sinhala too, as the family will read it', ((await billCard.locator('.claim-other p[lang="si"]').innerText().catch(() => '')) || '').includes('තැපැල්'));
  await billCard.locator('button', { hasText: 'Edit wording' }).click();
  await billCard.locator('textarea[lang="si"]').fill('විදුලි බිල ළඟම තැපැල් කන්තෝරුවෙන් ගෙවන්න.');
  const decided = rp.waitForResponse((r) => r.url().includes('/decide'), { timeout: 10000 });
  await billCard.locator('button', { hasText: 'Accept' }).click();
  await decided;
  const fixed = (await (await fetch(`${BASE}/api/h/${rhid}/claims`, { headers: { Authorization: `Bearer ${rtoken}` } })).json()).claims.find((c) => c.text_si === 'විදුලි බිල ළඟම තැපැල් කන්තෝරුවෙන් ගෙවන්න.');
  check('edit: fixing only the translation keeps the owner’s own words', !!fixed && fixed.text_en === 'Pay the electricity bill at the post office.' && !(fixed.untranslated || []).length, JSON.stringify(fixed && { en: fixed.text_en, untranslated: fixed.untranslated }));

  const kasun = rlinks.people.find((p) => p.person_id === 'p-kasun');
  const kctx = await browser.newContext({ viewport: { width: 375, height: 812 }, reducedMotion: 'reduce' });
  const kp = await kctx.newPage();
  await kp.goto(`${BASE}${new URL(kasun.url).pathname}`, { waitUntil: 'networkidle' });
  await kp.waitForSelector('.board-hero');
  check('removed: Kasun’s phone opens the home before', (await kp.locator('.board-hero').count()) === 1);
  await fetch(`${BASE}/api/h/${rhid}/people/p-kasun`, { method: 'DELETE', headers: { Authorization: `Bearer ${rtoken}` } });
  await kp.reload({ waitUntil: 'networkidle' });
  await kp.waitForSelector('.center-page .state', { timeout: 10000 }).catch(() => {});
  check('removed: his link stops working at once', ((await kp.locator('.center-page .state').count()) ? await kp.locator('.center-page .state').innerText() : '').includes('doesn’t work any more'));
  check('removed: and his phone lets go of the home', await kp.evaluate((id) => !JSON.parse(localStorage.getItem('iid.tokens') || '{}')[id], rhid));
  await kctx.close();

  const oldSticker = rlinks.stickers.find((x) => x.task_key === 'water_pump');
  await rp.goto(`${BASE}/h/${rhid}/card?tab=links`, { waitUntil: 'networkidle' });
  await rp.locator('.danger-zone button', { hasText: 'Replace all links and stickers' }).click();
  await rp.locator('.danger-zone button', { hasText: 'Yes, replace them' }).click();
  await rp.waitForTimeout(500);
  const sctx2 = await browser.newContext({ viewport: { width: 375, height: 812 } });
  const sp2 = await sctx2.newPage();
  await sp2.goto(`${BASE}${new URL(oldSticker.url).pathname}`, { waitUntil: 'networkidle' });
  await sp2.waitForSelector('.center-page .state', { timeout: 10000 }).catch(() => {});
  check('replaced: an old sticker stops working', ((await sp2.locator('.center-page .state').count()) ? await sp2.locator('.center-page .state').innerText() : '').includes('doesn’t work any more'));
  await sctx2.close();
  await rp.goto(`${BASE}/h/${rhid}`, { waitUntil: 'networkidle' });
  check('replaced: the owner carries on with the new link', (await rp.locator('.board-hero').count()) === 1);
  const rtoken2 = await rp.evaluate((id) => JSON.parse(localStorage.getItem('iid.tokens'))[id], rhid);
  await fetch(`${BASE}/api/h/${rhid}`, { method: 'DELETE', headers: { Authorization: `Bearer ${rtoken2}` } });
  await rctx.close();

  // 13. Offline, for real. The browser's offline switch doesn't reach the service worker, so a
  // phone here reaches the server through a relay that is then switched off: after that,
  // nothing (page or service worker) can reach the server, as in a power cut.
  // The relay also adds "Vary: origin" to every answer, as a Hugging Face Space does: the app's
  // script is asked for with an Origin header and was saved without one, and the saved copy must
  // still open (on the hosted copy it didn't: a blank page, 1 November).
  const relay = await startRelay(new URL(BASE), { http: true, vary: 'origin' });
  const octx = await browser.newContext({ viewport: { width: 375, height: 812 }, reducedMotion: 'reduce' });
  await octx.addInitScript(() => {
    try {
      if (!localStorage.getItem('iid.lang')) localStorage.setItem('iid.lang', 'en');
    } catch (e) {}
  });
  const op = await octx.newPage();
  op.on('pageerror', (e) => errors.push(`pageerror, offline: ${e}`));
  await op.goto(`${relay.base}/try`, { waitUntil: 'networkidle' });
  await op.waitForSelector('.board-hero');
  const ohid = new URL(op.url()).pathname.split('/')[2];
  const otoken = await op.evaluate((id) => JSON.parse(localStorage.getItem('iid.tokens'))[id], ohid);
  const olinks = await (await fetch(`${BASE}/api/h/${ohid}/links`, { headers: { Authorization: `Bearer ${otoken}` } })).json();
  const osticker = olinks.stickers.find((s) => s.task_key === 'main_switch');
  await op.goto(`${relay.base}/h/${ohid}/card?tab=offline`, { waitUntil: 'networkidle' });
  await op.evaluate(() => navigator.serviceWorker && navigator.serviceWorker.ready);
  await op.reload({ waitUntil: 'networkidle' });
  await op.locator('button', { hasText: 'Save for offline' }).click();
  await op.waitForSelector('.offline .ok-note', { timeout: 30000 });
  check('offline: saved on this phone', (await op.locator('.offline .ok-note').innerText()).includes('Saved'));
  await relay.close();
  await octx.setOffline(true);
  check('offline: the server really is out of reach', !(await reachable(`${relay.base}/api/health`)));
  await op.goto(`${relay.base}/h/${ohid}`, { waitUntil: 'domcontentloaded' }).catch(() => {});
  await op.waitForSelector('.board-hero', { timeout: 10000 }).catch(() => {});
  check('offline: the board still opens with no connection', (await op.locator('.board-hero').count()) === 1);
  check('offline: says it is offline', (await op.locator('.offline-bar').count()) === 1);
  await op.goto(`${relay.base}${new URL(osticker.url).pathname}`, { waitUntil: 'domcontentloaded' }).catch(() => {});
  await op.waitForSelector('.sticker-main h1', { timeout: 10000 }).catch(() => {});
  check(
    'offline: a sticker opens its job from the saved pack',
    (await op.locator('.sticker-main h1').count()) === 1 && (await op.locator('.sticker-main h1').innerText()) === 'Main switch box',
  );
  check('offline: the sticker page says it is the saved copy', (await op.locator('.sticker-page .offline-bar').count()) === 1);
  await op.waitForSelector('.sticker-main figure.clip', { timeout: 10000 }).catch(() => {});
  check('offline: the sticker still shows its clip', (await op.locator('.sticker-main figure.clip').count()) === 1);
  await shot(op, '09-sticker-offline');
  await octx.close();
  await fetch(`${BASE}/api/h/${ohid}`, { method: 'DELETE', headers: { Authorization: `Bearer ${otoken}` } });

  // 13b. When a piece can't be saved, the pack says so; and this phone's copy can be removed.
  // Service workers are off here so the blocked clips really fail.
  const pctx = await browser.newContext({ viewport: { width: 375, height: 812 }, reducedMotion: 'reduce', serviceWorkers: 'block' });
  await pctx.addInitScript(() => {
    try {
      if (!localStorage.getItem('iid.lang')) localStorage.setItem('iid.lang', 'en');
    } catch (e) {}
  });
  await pctx.route('**/jobs/**', (route) => route.abort());
  const pp = await pctx.newPage();
  await pp.goto(`${BASE}/try`);
  await pp.waitForURL(/\/h\/demo-/, { timeout: 15000 });
  const phid = new URL(pp.url()).pathname.split('/')[2];
  await pp.goto(`${BASE}/h/${phid}/card?tab=offline`, { waitUntil: 'networkidle' });
  await pp.locator('button', { hasText: 'Save for offline' }).click();
  await pp.waitForSelector('.offline .warn-note', { timeout: 30000 }).catch(() => {});
  const partial = (await pp.locator('.offline .warn-note').count()) ? await pp.locator('.offline .warn-note').innerText() : '';
  check('offline: a pack with pieces missing says so', partial.includes('didn’t save'), partial.slice(0, 90));
  check('offline: and is not called complete', (await pp.locator('.offline .ok-note').count()) === 0);
  await pp.locator('button', { hasText: 'Remove from this phone' }).click();
  await pp.waitForSelector('.toast:has-text("Removed from this phone")', { timeout: 5000 }).catch(() => {});
  const left = await pp.evaluate(async (id) => {
    const c = await caches.open('iid-offline-v1');
    return (await c.keys()).filter((k) => new URL(k.url).pathname.startsWith(`/api/h/${id}/`)).length;
  }, phid);
  check('offline: this phone’s copy can be removed, apart from the home', left === 0, `${left} left`);
  await pp.goto(`${BASE}/h/${phid}/task/main_switch`, { waitUntil: 'networkidle' });
  await pp.waitForSelector('.clip-unavailable', { timeout: 15000 }).catch(() => {});
  check('clip: when a clip can’t be had, the page says so and shows the still', ((await pp.locator('.clip-unavailable').count()) ? await pp.locator('.clip-unavailable').innerText() : '').includes('can’t play here'));
  const ptoken = await pp.evaluate((id) => JSON.parse(localStorage.getItem('iid.tokens'))[id], phid);
  await fetch(`${BASE}/api/h/${phid}`, { method: 'DELETE', headers: { Authorization: `Bearer ${ptoken}` } });
  await pctx.close();

  // 14. Public pages and not found
  await page.goto(`${BASE}/rules`, { waitUntil: 'networkidle' });
  check('rules: fingerprint matches', (await page.locator('.chain').innerText()).includes('matches'));
  await axe(page, 'rules');
  await page.goto(`${BASE}/credits`, { waitUntil: 'networkidle' });
  check('credits: photos credited', (await page.locator('.credit-list li').count()) >= 12);
  await page.goto(`${BASE}/nowhere`, { waitUntil: 'networkidle' });
  check('not found page', (await page.locator('.center-page').innerText()).includes('doesn’t exist'));
  const api404 = await fetch(`${BASE}/api/nowhere`);
  check('unknown API paths return 404, not the app', api404.status === 404, String(api404.status));

  // 15. Delete everything
  await page.goto(`${BASE}/h/${hid}/people`, { waitUntil: 'networkidle' });
  await page.locator('.danger-zone input').fill('DELETE');
  await page.locator('.danger-zone button.btn-danger').click();
  await page.waitForURL(`${BASE}/`, { timeout: 10000 });
  const gone = await fetch(`${BASE}/api/h/${hid}/board`, { headers: { Authorization: `Bearer ${token}` } });
  check('delete: the home is gone', gone.status === 404 || gone.status === 401, String(gone.status));

  // 16. Desktop sizes
  const wide = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce' });
  const wp = await wide.newPage();
  await wp.goto(`${BASE}/`, { waitUntil: 'networkidle' });
  await noOverflow(wp, 'landing 1440px');
  await shot(wp, '09-landing-desktop');
  await wide.close();

  // 17. The guided tour, on a first visit
  const tourErrors = [];
  const watch = (pg) => {
    pg.on('pageerror', (e) => tourErrors.push(`pageerror: ${e}`));
    pg.on('console', (m) => {
      if (m.type() === 'error' && !/Failed to load resource: the server responded with a status of (401|404|410)/.test(m.text())) tourErrors.push(`console: ${m.text()}`);
    });
  };
  {
    const tctx = await browser.newContext({ viewport: { width: 1280, height: 860 }, reducedMotion: 'reduce', tour: true });
    await tctx.addInitScript(() => {
      try {
        if (!localStorage.getItem('iid.lang')) localStorage.setItem('iid.lang', 'en');
      } catch (e) {}
    });
    const tp = await tctx.newPage();
    watch(tp);
    await tp.goto(`${BASE}/`, { waitUntil: 'networkidle' });
    check('tour: a first visit opens the welcome card', await tp.locator('.tour-modal[role="dialog"]').isVisible());
    await axe(tp, 'tour welcome');
    await shot(tp, '20-tour-welcome');
    await tp.locator('.tour-modal button', { hasText: 'Start the tour' }).click();
    await tp.waitForURL(/\/h\/demo-/, { timeout: 20000 });
    const stops = [
      ['', '.board-hero'], ['', '.timeline'], ['', '.job-list'], ['/record', '.pipeline'], ['/review', '.claims .claim'], ['/review', '.left-out'],
      ['/task/main_switch', '.task-clip'], ['/prove', 'section.proof-card[aria-labelledby="show-title"]'], ['/prove', 'section.proof-card[aria-labelledby="tell-title"]'],
      ['/help', '.suggest'], ['/help', '.wa'], ['/card', '.stickers'], ['/card', '.offline'], ['/evidence', '.chain'],
    ];
    const misses = [];
    for (let i = 0; i < stops.length; i++) {
      const [route, sel] = stops[i];
      await tp.waitForFunction((n) => document.querySelector('.tour-count')?.textContent.includes(`Step ${n} of`), i + 1, { timeout: 15000 });
      const lit = await tp
        .waitForFunction(
          (s) => {
            const spot = document.querySelector('.tour-spot');
            const el = document.querySelector(s);
            if (!spot || !el || getComputedStyle(spot).opacity !== '1') return false;
            const a = spot.getBoundingClientRect();
            const b = el.getBoundingClientRect();
            const w = Math.max(0, Math.min(a.right, b.right) - Math.max(a.left, b.left));
            const h = Math.max(0, Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top));
            return w * h > 0.6 * a.width * a.height;
          },
          sel,
          { timeout: 12000 },
        )
        .then(() => true)
        .catch(() => false);
      const pathNow = new URL(tp.url()).pathname;
      const onPage = route ? pathNow.endsWith(route) : /^\/h\/demo-[^/]+$/.test(pathNow);
      if (!lit || !onPage) misses.push(`step ${i + 1} ${route || 'board'} ${sel}${lit ? '' : ' not lit'}${onPage ? '' : ` on ${pathNow}`}`);
      if (i === 0) await axe(tp, 'tour step');
      if (i === 7) await shot(tp, '21-tour-show-me');
      await tp.locator('.tour-next').click();
    }
    check('tour: each of the 14 steps opens its page and spotlights its part', misses.length === 0, misses.join('; '));
    check('tour: the last step leads to the finish card', await tp.locator('.tour-modal h2', { hasText: 'stays home' }).isVisible());
    await tp.locator('.tour-modal button', { hasText: 'Explore on my own' }).click();
    check('tour: closing it leaves the app to use', (await tp.locator('.tour-card, .tour-modal').count()) === 0);
    await tp.locator('.topbar-tour').click();
    await tp.waitForSelector('.tour-card');
    check('tour: the compass in the top bar starts it again', (await tp.locator('.tour-count').innerText()).includes('Step 1 of'));
    await tp.locator('.tour-next').click();
    await tp.waitForFunction(() => document.querySelector('.tour-count')?.textContent.includes('Step 2 of'));
    await tp.locator('.tour-back').click();
    const backOk = await tp.waitForFunction(() => document.querySelector('.tour-count')?.textContent.includes('Step 1 of'), null, { timeout: 5000 }).then(() => true).catch(() => false);
    check('tour: Back returns to the step before', backOk);
    await tp.keyboard.press('Escape');
    check('tour: Escape ends it', (await tp.locator('.tour-card').count()) === 0);
    await tp.reload({ waitUntil: 'networkidle' });
    check('tour: once closed, it does not open again by itself', (await tp.locator('.tour-card, .tour-modal').count()) === 0);
    await tp.goto(`${BASE}/`, { waitUntil: 'networkidle' });
    check('tour: the landing page offers it again', await tp.locator('.tour-launch').isVisible());
    await tctx.close();

    const mctx = await browser.newContext({ viewport: { width: 375, height: 812 }, reducedMotion: 'reduce', tour: true });
    const mp = await mctx.newPage();
    watch(mp);
    await mp.goto(`${BASE}/try`);
    const direct = await mp.waitForSelector('.tour-modal', { timeout: 20000 }).then(() => true).catch(() => false);
    check('tour: opening the sample home straight away offers it too', direct);
    await noOverflow(mp, 'tour welcome 375px');
    await mp.locator('.tour-modal button', { hasText: 'Start the tour' }).click();
    const sheets = [];
    for (let i = 0; i < 5; i++) {
      await mp.waitForFunction((n) => document.querySelector('.tour-count')?.textContent.includes(`Step ${n} of`), i + 1, { timeout: 15000 });
      await mp.waitForFunction(() => getComputedStyle(document.querySelector('.tour-spot')).opacity === '1', null, { timeout: 12000 }).catch(() => {});
      await mp.waitForTimeout(700);
      sheets.push(
        await mp.evaluate(() => {
          const c = document.querySelector('.tour-card').getBoundingClientRect();
          const s = document.querySelector('.tour-spot').getBoundingClientRect();
          return { place: document.querySelector('.tour-card').dataset.place, above: s.top < c.top - 60, fits: c.left >= 0 && c.right <= innerWidth };
        }),
      );
      if (i === 4) await shot(mp, '22-tour-375');
      await mp.locator('.tour-next').click();
    }
    check('tour 375px: a sheet at the bottom, with the spotlit part showing above it', sheets.every((s) => s.place === 'sheet' && s.above && s.fits), JSON.stringify(sheets));
    await noOverflow(mp, 'tour 375px');
    await mctx.close();
  }
  check('tour: no script errors', tourErrors.length === 0, tourErrors.slice(0, 5).join(' | '));

  check('no script errors on any page', errors.length === 0, errors.slice(0, 5).join(' | '));
  await browser.close();
  console.log(`\n${results.length - failed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})().catch((err) => {
  console.error(err);
  process.exit(2);
});
