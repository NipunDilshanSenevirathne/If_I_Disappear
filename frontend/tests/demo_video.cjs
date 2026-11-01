/* A captioned, silent walk-through of the sample home, recorded from a running server.
   A starting point for the demo video: add a voice-over, or use it as it is.

     BASE=http://127.0.0.1:8080 OUT=docs/demo node frontend/tests/demo_video.cjs
     # then: ffmpeg -i docs/demo/raw.webm -c:v libx264 -crf 24 -pix_fmt yuv420p -movflags +faststart docs/demo/demo.mp4

   Captions are drawn into the page itself, so what you see is what was really on screen. */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const BASE = process.env.BASE || 'http://127.0.0.1:8080';
const OUT = process.env.OUT || 'docs/demo';
// A 1280 x 720 video of the page zoomed to 4/3, so the app fills the frame and text is easy to read.
const W = 1280;
const H = 720;
const ZOOM = 4 / 3;

async function caption(page, text, ms = 3200) {
  await page.evaluate((t) => {
    let el = document.getElementById('demo-caption');
    if (!el) {
      el = document.createElement('div');
      el.id = 'demo-caption';
      Object.assign(el.style, {
        position: 'fixed', left: '50%', bottom: '86px', transform: 'translateX(-50%)', zIndex: '99999', width: 'max-content',
        maxWidth: '820px', padding: '12px 20px', borderRadius: '14px', background: 'rgba(16,33,42,0.94)',
        color: '#fff', font: '600 20px/1.35 Outfit Variable, system-ui, sans-serif', textAlign: 'center',
        boxShadow: '0 10px 30px rgba(0,0,0,0.35)', border: '1px solid rgba(247,181,71,0.55)', pointerEvents: 'none',
      });
      document.body.appendChild(el);
    }
    el.textContent = t;
    el.style.display = 'block';
  }, text);
  await page.waitForTimeout(ms);
  // Hidden again before the next click, so a caption never sits over the screen that follows.
  await page.evaluate(() => {
    const el = document.getElementById('demo-caption');
    if (el) el.style.display = 'none';
  });
}

async function smoothScrollTo(page, selector, offset = -90) {
  await page.evaluate(({ s, o }) => {
    const el = document.querySelector(s);
    if (el) window.scrollTo({ top: el.getBoundingClientRect().top + window.scrollY + o, behavior: 'smooth' });
  }, { s: selector, o: offset });
  await page.waitForTimeout(900);
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: W, height: H }, recordVideo: { dir: OUT, size: { width: W, height: H } } });
  await ctx.addInitScript((zoom) => {
    try {
      localStorage.setItem('iid.lang', 'en');
    } catch (e) {}
    document.addEventListener('DOMContentLoaded', () => {
      const style = document.createElement('style');
      style.textContent = `html { zoom: ${zoom}; }`;
      document.head.appendChild(style);
    });
  }, ZOOM);
  const p = await ctx.newPage();

  await p.goto(`${BASE}/`, { waitUntil: 'networkidle' });
  await caption(p, 'When a parent leaves Sri Lanka to work abroad, the house still has to run.', 3600);
  await caption(p, 'If I Disappear turns one walk through the house into checked, bilingual steps.', 3200);
  await smoothScrollTo(p, '#witnesses', -40);
  await caption(p, 'Every fact is checked by up to three witnesses: the exact words, the picture, and a second reading.', 3600);

  // From here on the app is used by clicking, the way a person would.
  await p.locator('a[href="/try"]').first().click();
  await p.waitForURL(/\/h\/demo-/, { timeout: 20000 });
  await p.waitForSelector('.board-hero');
  await caption(p, 'The sample home. If Dilini left tomorrow, 4 of her 6 household jobs would stop.', 3800);
  await smoothScrollTo(p, '#jobs');
  await caption(p, 'Real recorded runs of Muse Spark 1.3, Muse Wonder and SAM 3.1. Every check runs live.', 3400);

  await p.locator('.job-card', { hasText: 'Main switch box' }).click();
  await p.waitForSelector('.clip-stage');
  await smoothScrollTo(p, '.steps', -260);
  await caption(p, 'Each step keeps Dilini’s own Sinhala words, and the second she said them.', 2800);
  await smoothScrollTo(p, '.clip-stage', -70);
  await p.evaluate(() => {
    const v = document.querySelector('.clip-stage video');
    if (v) {
      v.muted = true;
      v.currentTime = 0.5;
      v.play();
    }
  });
  await caption(p, 'SAM 3.1 follows the switch box through her clip.', 4200);

  await p.locator('.bottomnav-item', { hasText: 'Prove' }).click();
  await p.waitForSelector('.pick-chip');
  await p.locator('.pick-chip', { hasText: 'Nethum' }).click();
  await p.locator('.pick-job', { hasText: 'Water pump' }).click();
  await p.waitForSelector('.sample-photo');
  await caption(p, 'Before she leaves, Nethum proves he can run the water pump.', 2400);
  await smoothScrollTo(p, '.sample-photo', -160);
  await p.locator('.sample-photo', { hasText: 'A different one' }).click();
  await p.waitForSelector('.verdict');
  await caption(p, 'A photo with no pump in it: SAM 3.1 finds no water pump, so it can’t pass, and the app asks for another photo.', 3400);
  await p.locator('.sample-photo', { hasText: 'The right one' }).click();
  await p.waitForSelector('.verdict-pass');
  await smoothScrollTo(p, '.proof-photo', -120);
  await caption(p, 'The right pump: SAM 3.1 outlines it, and Muse Spark matches it to the one Dilini showed.', 3800);
  await smoothScrollTo(p, '.sample-answer', -160);
  await p.locator('.sample-answer', { hasText: 'I switch the pump on' }).click();
  await p.waitForFunction(() => document.querySelectorAll('.proof-card')[1]?.querySelector('.verdict'));
  await caption(p, 'Then he explains it. He forgets what to do if it grinds, so it fails.', 3200);
  await p.locator('.sample-answer', { hasText: 'grinding noise' }).click();
  await p.waitForSelector('.celebrate', { timeout: 10000 });
  await smoothScrollTo(p, '.celebrate', -200);
  await caption(p, 'Every point covered: the water pump turns green.', 3000);

  await p.locator('.bottomnav-item', { hasText: 'Help' }).click();
  await p.waitForSelector('#ask');
  await p.fill('#ask', 'The pump is making a grinding noise');
  await p.locator('form.ask button[type=submit]').click();
  await p.waitForSelector('.answer h2');
  await smoothScrollTo(p, '.asked', -60);
  await caption(p, 'While she is away, the help line answers only with what she recorded.', 3400);
  await p.fill('#ask', 'I can smell gas in the kitchen');
  await p.locator('form.ask button[type=submit]').click();
  await p.waitForSelector('.answer-emergency');
  await smoothScrollTo(p, '.answer-emergency', -140);
  await caption(p, 'A gas smell is an emergency: code shows Sri Lanka’s numbers before any model runs.', 3600);

  await p.locator('.topbar .menu .icon-btn').click();
  await p.locator('.menu-panel button', { hasText: 'Review' }).click();
  await p.waitForSelector('.claim');
  await smoothScrollTo(p, '.claim.claim-needs_review', -100);
  await caption(p, 'Here two Meta models disagreed about where the files are. The rules don’t guess: a person decides.', 4200);
  await p.locator('.tabs button', { hasText: 'Not used' }).click();
  await p.waitForTimeout(400);
  await caption(p, 'And medicine instructions are never turned into steps.', 3000);

  await p.locator('.bottomnav-item', { hasText: 'Card' }).click();
  await p.locator('.tabs button', { hasText: 'Stickers' }).click();
  await p.waitForSelector('.sticker');
  await caption(p, 'A QR sticker for each object opens only its own job, even offline.', 3400);

  await p.locator('.bottomnav-item', { hasText: 'Home' }).click();
  await p.waitForSelector('.board-hero');
  await p.locator('.topbar .lang-toggle button[lang="si"]').click();
  await caption(p, 'Everything in English and Sinhala.', 2800);
  await p.locator('.topbar .lang-toggle button[lang="en"]').click();

  await p.locator('.topbar .menu .icon-btn').click();
  await p.locator('.menu-panel button', { hasText: 'How we know' }).click();
  await p.waitForSelector('.chain');
  await caption(p, 'Models read; code decides. Every step is in a log anyone can check.', 3600);

  await p.goto(`${BASE}/`, { waitUntil: 'networkidle' });
  await caption(p, 'If I Disappear. So what you know stays home.', 3400);

  const video = p.video();
  await ctx.close();
  const raw = await video.path();
  fs.renameSync(raw, path.join(OUT, 'raw.webm'));
  await browser.close();
  console.log('saved', path.join(OUT, 'raw.webm'));
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
