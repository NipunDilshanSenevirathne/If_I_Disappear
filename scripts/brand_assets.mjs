// Render the PNG icons and the social preview image from the SVG mark and the site photos.
//   node scripts/brand_assets.mjs
import { createRequire } from 'node:module';
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const require = createRequire(import.meta.url);
const { chromium } = require('playwright');
const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const pub = join(root, 'frontend', 'public');
const shapes = readFileSync(join(root, 'frontend', 'src', 'lib', 'landingShapes.ts'), 'utf8');
const body = shapes.slice(shapes.indexOf('Record<string, LandingShape> = ') + 'Record<string, LandingShape> = '.length);
const json = JSON.parse(body.slice(0, body.lastIndexOf('};') + 1));
const font = pathToFileURL(join(root, 'frontend', 'node_modules', '@fontsource-variable', 'outfit', 'files', 'outfit-latin-wght-normal.woff2')).href;

const browser = await chromium.launch();
const page = await browser.newPage();

for (const [svg, out, size] of [
  ['icon.svg', 'icon-192.png', 192],
  ['icon.svg', 'icon-512.png', 512],
  ['icon.svg', 'apple-touch-icon.png', 180],
  ['maskable.svg', 'maskable-512.png', 512],
]) {
  const markup = readFileSync(join(pub, 'icons', svg), 'utf8').replace('<svg ', `<svg width="${size}" height="${size}" `);
  await page.setViewportSize({ width: size, height: size });
  await page.setContent(`<html><body style="margin:0;background:transparent">${markup}</body></html>`);
  await page.locator('svg').screenshot({ path: join(pub, 'icons', out), omitBackground: true });
}

const img = (name) => pathToFileURL(join(pub, 'images', name)).href;
const card = (key, title, status, ok) => {
  const s = json[key];
  return `<figure class="card"><img src="${img(`pin-${key}-480.webp`)}"><svg viewBox="0 0 ${s.w} ${s.h}" preserveAspectRatio="xMidYMid slice"><path d="${s.d}" fill="rgba(247,181,71,.16)" stroke="#F7B547" stroke-width="5" stroke-linejoin="round" style="filter:drop-shadow(0 0 6px rgba(247,181,71,.9))"/></svg><figcaption><b>${title}</b><span style="color:${ok ? '#8fe0b2' : '#F7B547'}">${status}</span></figcaption></figure>`;
};
await page.setViewportSize({ width: 1200, height: 630 });
const og = `<!doctype html><html><head><style>
@font-face{font-family:Outfit;src:url(${font}) format('woff2');font-weight:100 900}
*{box-sizing:border-box}body{margin:0;width:1200px;height:630px;font-family:Outfit,sans-serif;color:#fff;background:#10212A;position:relative;overflow:hidden}
.bg{position:absolute;inset:0;background:url(${img('hero-1280.webp')}) 70% 40%/cover}
.shade{position:absolute;inset:0;background:radial-gradient(60% 60% at 80% 25%,rgba(247,181,71,.18),transparent 70%),linear-gradient(180deg,rgba(16,33,42,.55),rgba(16,33,42,.35) 40%,rgba(16,33,42,.92))}
.top{position:absolute;left:64px;top:56px;right:64px}
.brand{display:flex;align-items:center;gap:14px;font-size:30px;font-weight:650}
h1{margin:26px 0 0;font-size:62px;line-height:1.02;letter-spacing:-.03em;font-weight:650;max-width:900px}
p{margin:14px 0 0;font-size:24px;color:rgba(255,255,255,.8)}
.cards{position:absolute;left:64px;right:64px;bottom:44px;display:grid;grid-template-columns:repeat(3,1fr);gap:22px}
.card{position:relative;margin:0;height:200px;border-radius:20px;overflow:hidden;border:1px solid rgba(255,255,255,.16)}
.card img{width:100%;height:100%;object-fit:cover;filter:brightness(.92)}.card svg{position:absolute;inset:0;width:100%;height:100%}
figcaption{position:absolute;left:12px;right:12px;bottom:12px;padding:10px 12px;border-radius:12px;background:rgba(10,22,28,.8);display:grid;font-size:18px}
figcaption span{font-size:15px;font-weight:500}
</style></head><body><div class="bg"></div><div class="shade"></div>
<div class="top"><div class="brand">${readFileSync(join(pub, 'icons', 'icon.svg'), 'utf8').replace('<svg ', '<svg width="44" height="44" ')}If I Disappear</div>
<h1>When you’re away, what you know stays home.</h1><p>Film it once. Prove they can do it. In English and Sinhala.</p></div>
<div class="cards">${card('breaker', 'Main switch box', 'Proven by Kasun', true)}${card('pump', 'Water pump', 'Nethum is still learning', false)}${card('documents', 'Important documents', 'Proven by Seetha Amma', true)}</div>
</body></html>`;
// A file page can load the local photos and font; about:blank cannot.
const tmp = join(mkdtempSync(join(tmpdir(), 'iid-og-')), 'og.html');
writeFileSync(tmp, og);
await page.goto(pathToFileURL(tmp).href);
await page.evaluate(() => document.fonts.ready);
await page.waitForTimeout(300);
await page.screenshot({ path: join(pub, 'images', 'og.png') });
await browser.close();
console.log('icons and og.png written');
