/* Screenshots for the docs, from a running server in judge mode (the sample home).

     BASE=http://127.0.0.1:8080 OUT=docs/screenshots node frontend/tests/screenshots.cjs

   Phone screens are 390 x 844 at 2x; the landing page is 1440 x 900. Then
   python scripts/compose_overview.py makes the README's four-screen picture from them. */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const { startRelay } = require('./relay.cjs');

const BASE = process.env.BASE || 'http://127.0.0.1:8080';
const OUT = process.env.OUT || 'docs/screenshots';

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  const phone = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, reducedMotion: 'reduce' });
  await phone.addInitScript(() => {
    try {
      if (!localStorage.getItem('iid.lang')) localStorage.setItem('iid.lang', 'en');
    } catch (e) {}
  });
  const p = await phone.newPage();
  const snap = async (name, opts = {}) => {
    await p.waitForTimeout(opts.wait ?? 700);
    await p.screenshot({ path: path.join(OUT, `${name}.png`), fullPage: !!opts.full });
    console.log('saved', name);
  };

  await p.goto(`${BASE}/try`);
  await p.waitForURL(/\/h\/demo-/, { timeout: 20000 });
  await p.waitForSelector('.board-hero');
  const hid = p.url().split('/h/')[1].split(/[/?#]/)[0];
  await snap('board');

  await p.goto(`${BASE}/h/${hid}/task/main_switch`, { waitUntil: 'networkidle' });
  await p.waitForSelector('.clip-stage');
  await p.evaluate(() => {
    const v = document.querySelector('.clip-stage video');
    if (v) v.currentTime = 3;
  });
  await snap('task', { wait: 1500 });

  await p.goto(`${BASE}/h/${hid}/prove?person=p-nethum&task=water_pump`, { waitUntil: 'networkidle' });
  await p.locator('.sample-photo', { hasText: 'The right one' }).click();
  await p.waitForSelector('.verdict-pass');
  await p.locator('.proof-card').first().scrollIntoViewIfNeeded();
  await p.evaluate(() => window.scrollBy(0, -70));
  await snap('prove');

  await p.goto(`${BASE}/h/${hid}/review`, { waitUntil: 'networkidle' });
  await p.locator('.claim.claim-needs_review').scrollIntoViewIfNeeded();
  await p.evaluate(() => window.scrollBy(0, -80));
  await snap('review');
  await p.locator('.tabs button', { hasText: 'Not used' }).click();
  await p.waitForSelector('.left-out-medical');
  await p.locator('.left-out-medical').scrollIntoViewIfNeeded();
  await p.evaluate(() => window.scrollBy(0, -160));
  await snap('not-used');

  await p.goto(`${BASE}/h/${hid}/help`, { waitUntil: 'networkidle' });
  await p.locator('.wa-hints .chip-btn').nth(1).click();
  await p.waitForSelector('.wa-them:not(.wa-typing)');
  await p.locator('.wa').scrollIntoViewIfNeeded();
  await snap('whatsapp');
  await p.evaluate(() => window.scrollTo(0, 0));
  await p.fill('#ask', 'I can smell gas in the kitchen');
  await p.locator('form.ask button[type=submit]').click();
  await p.waitForSelector('.answer-emergency');
  await p.locator('.answer-emergency').scrollIntoViewIfNeeded();
  await p.evaluate(() => window.scrollBy(0, -170));
  await snap('help-gas');

  await p.goto(`${BASE}/h/${hid}/card`, { waitUntil: 'networkidle' });
  await p.waitForSelector('.fridge svg.qr');
  await snap('card');

  await p.goto(`${BASE}/h/${hid}/evidence`, { waitUntil: 'networkidle' });
  await p.waitForSelector('.chain');
  await snap('evidence');

  await p.goto(`${BASE}/h/${hid}`, { waitUntil: 'networkidle' });
  await p.locator('.topbar .lang-toggle button[lang="si"]').click();
  await snap('board-si');
  await p.locator('.topbar .lang-toggle button[lang="en"]').click();

  const token = await p.evaluate((id) => JSON.parse(localStorage.getItem('iid.tokens'))[id], hid);
  const links = await (await fetch(`${BASE}/api/h/${hid}/links`, { headers: { Authorization: `Bearer ${token}` } })).json();
  const sticker = links.stickers.find((s) => s.task_key === 'water_pump');
  const other = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, reducedMotion: 'reduce' });
  const sp = await other.newPage();
  await sp.goto(`${BASE}${new URL(sticker.url).pathname}`, { waitUntil: 'networkidle' });
  await sp.waitForSelector('.sticker-main h1');
  await sp.waitForTimeout(700);
  await sp.screenshot({ path: path.join(OUT, 'sticker.png') });
  console.log('saved sticker');
  await other.close();

  // A sticker with no connection, on a phone that saved the offline pack (through a relay that
  // is then switched off, so the service worker is offline too).
  const relay = await startRelay(new URL(BASE));
  const off = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, reducedMotion: 'reduce' });
  await off.addInitScript(() => {
    try {
      if (!localStorage.getItem('iid.lang')) localStorage.setItem('iid.lang', 'en');
    } catch (e) {}
  });
  const op = await off.newPage();
  await op.goto(`${relay.base}/try`);
  await op.waitForURL(/\/h\/demo-/, { timeout: 20000 });
  await op.waitForSelector('.board-hero');
  const ohid = op.url().split('/h/')[1].split(/[/?#]/)[0];
  const otoken = await op.evaluate((id) => JSON.parse(localStorage.getItem('iid.tokens'))[id], ohid);
  const olinks = await (await fetch(`${BASE}/api/h/${ohid}/links`, { headers: { Authorization: `Bearer ${otoken}` } })).json();
  const ost = olinks.stickers.find((s) => s.task_key === 'main_switch');
  await op.goto(`${relay.base}/h/${ohid}/card?tab=offline`, { waitUntil: 'networkidle' });
  await op.evaluate(() => navigator.serviceWorker && navigator.serviceWorker.ready);
  await op.reload({ waitUntil: 'networkidle' });
  await op.locator('button', { hasText: 'Save for offline' }).click();
  await op.waitForSelector('.offline .ok-note', { timeout: 30000 });
  await relay.close();
  await off.setOffline(true);
  await op.goto(`${relay.base}${new URL(ost.url).pathname}`, { waitUntil: 'domcontentloaded' }).catch(() => {});
  await op.waitForSelector('.sticker-main figure.clip', { timeout: 15000 });
  await op.waitForTimeout(900);
  await op.screenshot({ path: path.join(OUT, 'sticker-offline.png') });
  console.log('saved sticker-offline');
  await off.close();
  await fetch(`${BASE}/api/h/${ohid}`, { method: 'DELETE', headers: { Authorization: `Bearer ${otoken}` } });

  const wide = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce' });
  const wp = await wide.newPage();
  await wp.goto(`${BASE}/`, { waitUntil: 'networkidle' });
  await wp.waitForTimeout(1200);
  await wp.screenshot({ path: path.join(OUT, 'landing.png') });
  console.log('saved landing');
  await browser.close();
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
