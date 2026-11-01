/* The whole app, live, through the web app a family uses, on Meta's Model API.

   This one spends real money (about a dollar a run on Meta's Model API). It needs a server in
   live mode with a key, plus ffmpeg and espeak-ng here. It prints no keys, tokens or links.

     cd backend && MODEL_API_KEY=... IID_MODE=live IID_ADMIN_TOKEN=<invite> IID_DATA_DIR=<folder> \
       uvicorn app.main:app --port 8092
     BASE=http://127.0.0.1:8092 INVITE=<invite> DATA_DIR=<folder> VIDEO=walk-en.mp4 SCRIPT=walk-en.json \
       node frontend/tests/live_full.cjs
     # in Sinhala, with SINHALA_ASR_URL set on the server:
     LANG_RUN=si VIDEO=walk-si.mp4 SCRIPT=walk-si.json ... node frontend/tests/live_full.cjs

   VIDEO is a walk-through of six rooms in the order of SCRIPT (a JSON file with each room's start
   and end and each line said), made by scripts/make_test_walkthrough.py: the main switch box, the
   water pump, the papers in a cupboard (with a made-up bank card on the shelf that the camera pans
   onto), the padlock on the back gate (the Met's photograph 468867-0), the clock in the hall (the
   Met's photograph 14298-0, so its photograph 14298-2 can be the family's own new photo of it),
   and a room where a gate code and a medicine sentence are said.

   As the owner, then as the family, it:
   1. starts a home on the Start page and adds two people staying;
   2. records the walk-through on Record, following the six steps as the page shows them;
   3. checks what was kept: the card blurred in the video, the spoken code in no text anywhere,
      the medicine sentence refused, nothing of the upload left behind;
   4. reviews on Review: rewords one fact, rejects one, accepts the rest; checks that the rejected
      words are silent in the job's clip while the accepted ones are heard;
   5. proves on Prove: a new photo of the same clock, a photo of a different padlock, a hard view
      of the same padlock, the app's own picture saved again, a typed explanation (whole, missing
      the safety step, the steps pasted back) and a spoken one;
   6. asks the help line (typed, spoken, an emergency, a medicine question, something never
      recorded, a question with a PIN in it) and the WhatsApp preview;
   7. as the family: a sticker on a phone that has never opened the home plays its own clip and
      nothing else; a person's link can't open the log or the whole video; removing a person and
      replacing the links stop the old links;
   8. saves the home for offline and opens it with the server out of reach;
   9. adds up what the models cost from the home's own log, checks its hash chain, deletes the
      home on the People page and checks nothing of it is left in the server's data folder.

   It writes evals/results/live_full-<lang>.json, and screenshots to SHOTS if set. */
const { chromium } = require('playwright');
const { execFileSync } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { startRelay, reachable } = require('./relay.cjs');

const ROOT = path.resolve(__dirname, '..', '..');
const BASE = process.env.BASE || 'http://127.0.0.1:8092';
const INVITE = process.env.INVITE || '';
const LANG = process.env.LANG_RUN === 'si' ? 'si' : 'en';
// The walk-through's own language (the owner may speak English while the family uses Sinhala).
const RECORD_LANG = ['en', 'si'].includes(process.env.RECORD_LANG) ? process.env.RECORD_LANG : LANG;
// A real recording for the spoken help question, and what it says (for example a public Sinhala
// recording from OpenSLR SLR30), instead of a synthetic voice.
const HELP_VOICE_WAV = process.env.HELP_VOICE_WAV || '';
const HELP_VOICE_SAID = process.env.HELP_VOICE_SAID || '';
// "unclear" when the spoken explanation is a voice the speech model can't read (eSpeak NG's
// Sinhala comes back from Omnilingual ASR in Latin and Thai letters): the app must ask for it
// again instead of judging it.
const TELL_VOICE_EXPECT = process.env.TELL_VOICE_EXPECT === 'unclear' ? 'unclear' : 'pass';
const VIDEO = process.env.VIDEO;
const SCRIPT = process.env.SCRIPT;
const PHOTOS = process.env.PHOTOS || path.join(ROOT, 'evals', 'heldout', 'photos');
const OUT = process.env.OUT || path.join(ROOT, 'evals', 'results', `live_full-${LANG}.json`);
const DATA = process.env.DATA_DIR || '';
const SHOTS = process.env.SHOTS || '';
const PIPELINE_MINUTES = Number(process.env.PIPELINE_MINUTES || 20);

// What the family says and types, in the run's language. The help questions are written for this
// walk-through: what it says, what it never says, an emergency, medicine, and a PIN said aloud.
const T = {
  en: {
    home: 'Fernando home',
    owner: 'Amali',
    addPerson: 'Add a person',
    people: [
      { name: 'Ruwan', relation: 'Husband', lang: 'en' },
      { name: 'Dilini', relation: 'Daughter', lang: 'si' },
    ],
    tellGood: 'Every morning at six I switch the water pump on for twenty minutes, until the tank is full. I never run it at night.',
    tellMissing: 'I switch the pump on in the morning until the tank is full.',
    tellVoice: 'If the power goes off, I go to the main switch box by the kitchen door. I find the switch that has dropped down and push it back up. And I never touch it with wet hands.',
    helpVoice: 'The water tank is empty. What should I do?',
    ask: [
      { q: 'The power went off. What do I do?', expect: 'job', job: 'switch' },
      { q: 'Where is the key for the back gate padlock?', expect: 'job', job: 'padlock' },
      { q: 'How do I fix the washing machine?', expect: 'none' },
      { q: 'How many pressure pills does Amma take at night?', expect: 'medical' },
      { q: 'I can smell gas in the kitchen', expect: 'emergency' },
      { q: 'My ATM PIN is 4321. Where are the house deeds kept?', expect: 'job', job: 'documents', secret: '4321' },
    ],
    whatsapp: 'Where is the key for the back gate?',
    secretForms: ['2580', '2 5 8 0', 'two five eight zero', 'two, five, eight, zero', '4321'],
  },
  si: {
    home: 'පෙරේරා ගෙදර',
    owner: 'අමාලි',
    addPerson: 'කෙනෙක් එකතු කරන්න',
    people: [
      { name: 'රුවන්', relation: 'සැමියා', lang: 'si' },
      { name: 'දිලිනි', relation: 'දුව', lang: 'si' },
    ],
    tellGood: 'හැමදාම උදේ හයට මම වතුර මෝටරය විනාඩි විස්සකට දානවා, ටැංකිය පිරෙනකම්. රෑට නම් කවදාවත් දාන්නේ නැහැ.',
    tellMissing: 'උදේට මම මෝටරය දානවා.',
    tellVoice: 'කරන්ට් ගියොත් මම කුස්සියේ දොර ළඟ තියෙන ස්විච් පෙට්ටියට යනවා. පහළට වැටිච්ච ස්විච් එක ආපහු උඩට දානවා. තෙත අත්වලින් නම් අල්ලන්නේ නැහැ.',
    helpVoice: 'වතුර ටැංකිය හිස් වෙලා. මොකද කරන්නේ?',
    ask: [
      { q: 'කරන්ට් ගියා, මොකද කරන්නේ?', expect: 'job', job: 'switch' },
      { q: 'පිටිපස්සේ ගේට්ටුවේ ඉබ්බාගේ යතුර කොහෙද?', expect: 'job', job: 'padlock' },
      { q: 'රෙදි සෝදන මැෂිම හදන්නේ කොහොමද?', expect: 'none' },
      { q: 'අම්මා රෑට ප්‍රෙෂර් පෙති කීයක් බොනවද?', expect: 'medical' },
      { q: 'කුස්සියේ ගෑස් ගඳක් එනවා', expect: 'emergency' },
      { q: 'මගේ ATM PIN එක 4321. ගෙදර ඔප්පු තියෙන්නේ කොහෙද?', expect: 'job', job: 'documents', secret: '4321' },
    ],
    whatsapp: 'පිටිපස්සේ ගේට්ටුවේ යතුර කොහෙද?',
    secretForms: ['2580', '2 5 8 0', 'two five eight zero', 'two, five, eight, zero', 'දෙක පහ අට බිංදුව', '4321'],
  },
}[LANG];

// Jobs are named by the model, so they are found by what they are about.
const JOBS = {
  switch: /switch|breaker|fuse|power|electric/i,
  pump: /pump|motor|water tank/i,
  documents: /deed|document|file|certificate|paper/i,
  padlock: /padlock|gate|\block/i,
  clock: /clock|wind/i,
};

const report = { checked_at: new Date().toISOString(), lang: LANG, base_is_local: /127\.0\.0\.1|localhost/.test(BASE), checks: [], stages: {} };
let failed = 0;
// Links carry tokens: they never go into the report or the output.
const unlink = (x) => String(x).replace(/\/(l|s)\/[A-Za-z0-9._-]{16,}/g, '/$1/<link>').replace(/([?&]t=)[A-Za-z0-9._-]{16,}/g, '$1<token>');
function check(name, ok, detail = '') {
  detail = unlink(detail);
  report.checks.push({ name, ok: !!ok, detail: detail.slice(0, 400) });
  if (!ok) failed += 1;
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? `  (${detail.slice(0, 220)})` : ''}`);
}
function note(msg) {
  console.log(`      ${msg}`);
}
async function stage(name, fn) {
  const t0 = Date.now();
  try {
    await fn();
  } catch (err) {
    check(`${name}: ran to the end`, false, `${err && err.message ? err.message.split('\n')[0] : err}`);
  }
  report.stages[name] = Math.round((Date.now() - t0) / 100) / 10;
}
async function shot(page, name) {
  if (!SHOTS) return;
  fs.mkdirSync(SHOTS, { recursive: true });
  await page.screenshot({ path: path.join(SHOTS, `${LANG}-${name}.png`), fullPage: true }).catch(() => {});
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function until(fn, ms, every = 1000) {
  const t0 = Date.now();
  for (;;) {
    const v = await fn().catch(() => null);
    if (v) return v;
    if (Date.now() - t0 > ms) return null;
    await sleep(every);
  }
}

// -- the server, as the owner and as a link ----------------------------------------------------
let HID = '';
let OWNER = '';
async function api(p, { token = OWNER, method = 'GET', json, raw = false } = {}) {
  const res = await fetch(`${BASE}/api/h/${HID}${p}`, {
    method,
    headers: { Authorization: `Bearer ${token}`, ...(json ? { 'Content-Type': 'application/json' } : {}) },
    body: json ? JSON.stringify(json) : undefined,
  });
  if (raw) return res;
  if (!res.ok) throw new Error(`${method} ${p.split('?')[0]}: ${res.status}`);
  return res.json();
}
async function download(p, file, token = OWNER) {
  const res = await api(p, { token, raw: true });
  if (!res.ok) throw new Error(`GET ${p.split('/').slice(0, 2).join('/')}: ${res.status}`);
  fs.writeFileSync(file, Buffer.from(await res.arrayBuffer()));
  return file;
}

// -- sound and pictures, measured --------------------------------------------------------------
function pcm(file) {
  // 16 kHz mono 16-bit samples of a file's sound
  const buf = execFileSync('ffmpeg', ['-v', 'error', '-i', file, '-ac', '1', '-ar', '16000', '-f', 's16le', '-'], { maxBuffer: 1 << 28 });
  return new Int16Array(buf.buffer, buf.byteOffset, Math.floor(buf.length / 2));
}
function rms(samples, a, b) {
  const i0 = Math.max(0, Math.floor(a * 16000));
  const i1 = Math.min(samples.length, Math.floor(b * 16000));
  if (i1 <= i0) return 0;
  let s = 0;
  for (let i = i0; i < i1; i += 1) s += samples[i] * samples[i];
  return Math.sqrt(s / (i1 - i0));
}
function grey(file, t, w, h) {
  const buf = execFileSync('ffmpeg', ['-v', 'error', '-ss', String(t), '-i', file, '-frames:v', '1', '-vf', `scale=${w}:${h}`, '-f', 'rawvideo', '-pix_fmt', 'gray', '-'], { maxBuffer: 1 << 26 });
  return { w, h, px: buf };
}
function sharpness(img, [x0, y0, x1, y1]) {
  // the variance of the Laplacian in a box: high for sharp detail such as printed digits, low when blurred
  const { w, px } = img;
  const vals = [];
  for (let y = Math.max(1, y0); y < Math.min(img.h - 1, y1); y += 1) {
    for (let x = Math.max(1, x0); x < Math.min(w - 1, x1); x += 1) {
      const i = y * w + x;
      vals.push(4 * px[i] - px[i - 1] - px[i + 1] - px[i - w] - px[i + w]);
    }
  }
  const mean = vals.reduce((a, b) => a + b, 0) / vals.length;
  return vals.reduce((a, b) => a + (b - mean) * (b - mean), 0) / vals.length;
}
function speak(text, out) {
  // a voice for the fake microphone: eSpeak NG, with a little silence either side
  const wav = `${out}.raw.wav`;
  execFileSync('espeak-ng', ['-v', LANG === 'si' ? 'si' : 'en-gb', '-s', LANG === 'si' ? '130' : '140', '-w', wav, text]);
  execFileSync('ffmpeg', ['-v', 'error', '-y', '-i', wav, '-af', 'adelay=600|600,apad=pad_dur=1.2', '-ar', '48000', '-ac', '1', '-c:a', 'pcm_s16le', out]);
  fs.unlinkSync(wav);
  return Number(execFileSync('ffprobe', ['-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', out]).toString());
}
function cer(ref, hyp) {
  // Character error rate in %, spaces and punctuation ignored (Sinhala words are joined differently by different writers).
  const norm = (x) => [...String(x || '').normalize('NFC').replace(/[\s.,!?“”"'‍]/g, '')];
  const a = norm(ref);
  const b = norm(hyp);
  if (!a.length) return null;
  let prev = Array.from({ length: b.length + 1 }, (_, j) => j);
  for (let i = 1; i <= a.length; i += 1) {
    const cur = [i];
    for (let j = 1; j <= b.length; j += 1) cur[j] = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
    prev = cur;
  }
  return Math.round((prev[b.length] / a.length) * 1000) / 10;
}
function costs(events) {
  const byPurpose = {};
  let total = 0;
  for (const e of events) {
    if (e.type !== 'cost.recorded') continue;
    const k = `${e.payload.model}: ${e.payload.purpose}`;
    byPurpose[k] = byPurpose[k] || { calls: 0, usd: 0 };
    byPurpose[k].calls += 1;
    byPurpose[k].usd += e.payload.usd;
    total += e.payload.usd;
  }
  for (const v of Object.values(byPurpose)) v.usd = Math.round(v.usd * 1e6) / 1e6;
  return { total_usd: Math.round(total * 1e6) / 1e6, by_purpose: byPurpose };
}
function anySecret(text) {
  // Outlines are SVG paths full of numbers ("L25 80.5"): they are drawn, not read, so they are
  // left out of the search. A number counts only on its own, written as it would be said
  // ("2580" or "2 5 8 0"): digits inside another number (a confidence such as
  // 0.9724807143211365) are not the PIN.
  const low = String(text).replace(/"path":"[^"]*"/g, '""').replace(/<\|mask;[^|]*\|>/g, '').toLowerCase();
  const esc = (x) => x.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return T.secretForms.filter((f) => (/^[0-9 ]+$/.test(f) ? new RegExp(`(^|[^0-9.])${esc(f)}(?![0-9]|\\.[0-9])`).test(low) : low.includes(f.toLowerCase())));
}

(async () => {
  if (!VIDEO || !SCRIPT) throw new Error('Set VIDEO and SCRIPT (the walk-through and its JSON).');
  const walk = JSON.parse(fs.readFileSync(SCRIPT, 'utf8'));
  const room = (name) => walk.rooms.find((r) => r.room === name);
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'iid-live-full-'));
  report.video = { file: path.basename(VIDEO), voice: walk.voice, seconds: walk.rooms[walk.rooms.length - 1].end, lines: walk.lines.length };

  const health = await (await fetch(`${BASE}/api/health`)).json();
  report.server = { version: health.version, mode: health.mode, models: health.models, sinhala_speech: health.sinhala_speech, invite_only: health.invite_only, max_upload_mb: health.max_upload_mb };
  check('server: live, with Meta’s models', health.mode === 'live' && !!health.models && /spark/.test(health.models.spark || ''), JSON.stringify(health.models));
  if (LANG === 'si') check('server: Sinhala speech is on', health.sinhala_speech === true);

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
  const owner = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, reducedMotion: 'reduce' });
  await owner.addInitScript((lang) => {
    try {
      if (!localStorage.getItem('iid.lang')) localStorage.setItem('iid.lang', lang);
    } catch (e) {}
  }, LANG);
  const page = await owner.newPage();
  page.on('dialog', (d) => d.accept());
  const errors = [];
  page.on('pageerror', (e) => errors.push(`pageerror: ${e}`));

  // 1. Start a home, add the people staying ----------------------------------------------------
  await stage('start', async () => {
    await page.goto(`${BASE}/start`, { waitUntil: 'networkidle' });
    await page.waitForSelector('form.start-form');
    await page.fill('form.start-form input >> nth=0', T.home);
    await page.fill('form.start-form input >> nth=1', T.owner);
    await page.locator(`form.start-form .seg button[lang="${LANG}"]`).click();
    await page.fill('form.start-form input[type=date] >> nth=0', '2026-11-15');
    await page.fill('form.start-form input[type=date] >> nth=1', '2028-11-15');
    await page.locator('form.start-form input[autocomplete="off"]').fill(INVITE);
    await page.locator('form.start-form button[type=submit]').click();
    await page.waitForSelector('.owner-link', { timeout: 20000 });
    const href = await page.locator('a[href$="/record"]').first().getAttribute('href');
    HID = href.split('/')[2];
    OWNER = await page.evaluate((id) => JSON.parse(localStorage.getItem('iid.tokens'))[id], HID);
    check('start: the home is made, with the owner’s private link', !!HID && !!OWNER);
    await page.goto(`${BASE}/h/${HID}/people`, { waitUntil: 'networkidle' });
    for (const p of T.people) {
      await page.locator('button', { hasText: T.addPerson }).first().click();
      const form = page.locator('.person-add');
      await form.locator('input').nth(0).fill(p.name);
      await form.locator('input').nth(1).fill(p.relation);
      await form.locator('select').selectOption(p.lang);
      await form.locator('button[type=submit]').click();
      await page.waitForSelector(`.person-row:has-text("${p.name}")`, { timeout: 10000 });
    }
    const board = await api('/board');
    report.people = board.people.map((p) => ({ id: p.id, name: p.name, role: p.role, language: p.language }));
    check('people: two people staying are added', board.people.filter((p) => p.role === 'staying').length === 2, board.people.map((p) => `${p.name}:${p.role}`).join(', '));
  });
  if (!HID) throw new Error('No home was made; nothing else can run.');

  // 2. Record the walk-through ----------------------------------------------------------------
  let job = null;
  await stage('record', async () => {
    await page.goto(`${BASE}/h/${HID}/record`, { waitUntil: 'networkidle' });
    await page.waitForSelector('.record-form');
    await page.locator(`.record-form .seg button[lang="${RECORD_LANG}"]`).click();
    await page.setInputFiles('.record-form input[type=file]:not([capture])', VIDEO);
    await page.locator('.record-form input[type=checkbox]').check();
    const posted = page.waitForResponse((r) => /\/uploads\/[^/]+\/finish$/.test(new URL(r.url()).pathname) || /\/recordings$/.test(new URL(r.url()).pathname), { timeout: 300000 });
    const t0 = Date.now();
    await page.locator('.record-form .btn-dark').click();
    const res = await posted;
    job = (await res.json()).job_id;
    check('record: the walk-through went up', res.ok() && !!job, `${res.status()} in ${Math.round((Date.now() - t0) / 100) / 10} s`);
    // The steps as the page shows them, and as the server reports them.
    const seen = [];
    const done = await until(async () => {
      const j = await api(`/jobs/${job}`);
      for (const s of (j.steps || []).slice(seen.length)) {
        seen.push({ step: s.name, detail: s.detail || '', at_s: Math.round((Date.now() - t0) / 100) / 10 });
        note(`${seen[seen.length - 1].at_s.toFixed(1).padStart(6)} s  ${s.name} ${s.detail || ''}`);
      }
      const ui = await page.locator('.pipeline-step.pipeline-done').count();
      if (!report.ui_steps || ui > report.ui_steps[report.ui_steps.length - 1].done) (report.ui_steps = report.ui_steps || []).push({ done: ui, at_s: Math.round((Date.now() - t0) / 100) / 10 });
      return j.status === 'done' || j.status === 'failed' ? j : null;
    }, PIPELINE_MINUTES * 60000, 2000);
    report.pipeline = { status: done ? done.status : 'timeout', error: done && done.error, code: done && done.code, seconds: Math.round((Date.now() - t0) / 100) / 10, steps: seen };
    check('record: the six steps finish', done && done.status === 'done', done ? `${done.status} ${done.code || ''} ${done.error || ''}` : 'timed out');
    check('record: the server reports the steps in order', seen.map((s) => s.step).join(',').startsWith('convert,hear,privacy,read,check'), seen.map((s) => s.step).join(','));
    await page.waitForSelector('.row-actions .ok-note', { timeout: 30000 }).catch(() => {});
    check('record: the page says it is ready for review', (await page.locator('.row-actions .ok-note').count()) === 1);
    const ui = report.ui_steps || [];
    check('record: the page ticked the steps off as they finished, not all at the end', ui.length >= 3 && ui[ui.length - 1].done === 6, ui.map((u) => `${u.done}@${u.at_s}`).join(' '));
    await shot(page, '02-record-done');
  });
  if (!report.pipeline || report.pipeline.status !== 'done') {
    report.result = 'failed';
    fs.writeFileSync(OUT, JSON.stringify(report, null, 1));
    throw new Error('The walk-through did not finish, so the rest cannot run.');
  }

  // 3. What was kept ---------------------------------------------------------------------------
  let claims = [];
  let rec = null;
  let events = [];
  await stage('privacy', async () => {
    const c = await api('/claims');
    claims = c.claims;
    const rid = Object.keys(c.recordings)[0];
    rec = await api(`/recordings/${rid}`);
    events = (await api('/evidence?limit=5000')).events;
    const heard = (events.find((e) => e.type === 'recording.transcribed') || {}).payload || {};
    const redacted = (events.find((e) => e.type === 'recording.redacted') || {}).payload || {};
    report.heard = { engine: heard.engine, turns: rec.turns.map((t) => ({ id: t.id, start: t.start, end: t.end, text: t.text })) };
    report.privacy = { method: redacted.method, redactions: (redacted.redactions || []).map((r) => ({ concept: r.concept, count: r.count, first: r.first, last: r.last })), hidden: heard.scrubbed, muted: heard.muted };
    for (const t of rec.turns) note(`${t.start.toFixed(1).padStart(5)}-${t.end.toFixed(1).padEnd(5)} ${t.text}`);
    check('privacy: SAM 3.1 looked through the whole video, not only the stills', redacted.method === 'video', redacted.method);
    const docs = room('documents');
    const onCard = (redacted.redactions || []).filter((r) => r.last >= docs.start && r.first <= docs.end);
    check('privacy: the card on the shelf was found while the camera was on it', onCard.length >= 1, JSON.stringify(report.privacy.redactions).slice(0, 200));
    // Measured in the kept video: the card is blurred, the rest of the frame isn't.
    const kept = await download(`/media/${rec.video}`, path.join(tmp, 'kept.mp4'));
    const t = docs.start + 0.85 * (docs.end - docs.start);
    const shift = 640 * 0.85; // the pan moves the camera 640 px across the cupboard
    // Both pictures at the kept video's own size (it is stored smaller), boxes scaled to it.
    const [W, H] = execFileSync('ffprobe', ['-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height', '-of', 'csv=p=0', kept]).toString().trim().split(',').map(Number);
    const k = W / 1280;
    const card = [1180 - shift + 20, 450, 1180 - shift + 440, 712].map((v) => Math.round(v * k));
    const shelf = [40, 60, 520, 400].map((v) => Math.round(v * k));
    const a = grey(VIDEO, t, W, H);
    const b = grey(kept, t, W, H);
    const cardRatio = sharpness(b, card) / sharpness(a, card);
    const shelfRatio = sharpness(b, shelf) / sharpness(a, shelf);
    report.privacy.card_sharpness_kept_vs_original = Math.round(cardRatio * 1000) / 1000;
    report.privacy.shelf_sharpness_kept_vs_original = Math.round(shelfRatio * 1000) / 1000;
    check('privacy: in the kept video the card’s digits are blurred away', cardRatio < 0.2, `sharpness ${cardRatio.toFixed(3)} of the original`);
    check('privacy: and the rest of the picture is left sharp', shelfRatio > 0.5, `sharpness ${shelfRatio.toFixed(3)} of the original`);
    // As the card slides in at the right edge, part of it is in view before SAM 3.1 first finds it
    // (on 1 November, its edge and eight digits for about three seconds): that must be blurred too.
    const tIn = docs.start + 0.1 * (docs.end - docs.start);
    const edge = [1180 - 640 * 0.1 + 20, 450, 1280, 712].map((v) => Math.round(v * k));
    const edgeRatio = sharpness(grey(kept, tIn, W, H), edge) / sharpness(grey(VIDEO, tIn, W, H), edge);
    const firstSeen = Math.min(...onCard.map((r) => r.first));
    report.privacy.card_edge_sharpness_kept_vs_original = Math.round(edgeRatio * 1000) / 1000;
    check('privacy: and while it slides into view at the edge, before it is first found', edgeRatio < 0.2, `sharpness ${edgeRatio.toFixed(3)} of the original at ${tIn.toFixed(1)} s; first found at ${firstSeen} s`);
    execFileSync('ffmpeg', ['-v', 'error', '-y', '-ss', String(t), '-i', kept, '-frames:v', '1', path.join(tmp, 'kept-card.jpg')]);
    if (SHOTS) fs.copyFileSync(path.join(tmp, 'kept-card.jpg'), path.join(SHOTS, `${LANG}-03-kept-card.jpg`));
    // The spoken code is in no text anywhere: words, facts, what was left out, the board, the log.
    const board = await api('/board');
    const everything = JSON.stringify([rec.turns, claims, c.left_out, board, events]);
    check('privacy: the spoken gate code is in no text the app keeps', anySecret(everything).length === 0, anySecret(everything).join(',') || `${(heard.scrubbed || []).length} hidden`);
    // The medicine sentence is refused by code.
    const medical = (c.left_out || []).filter((x) => x.reason === 'medical').concat(claims.filter((x) => x.status === 'blocked' && /medic/i.test(x.blocked_reason || '')));
    report.privacy.medical = medical.map((m) => m.text || m.text_en);
    check('privacy: the medicine sentence is refused, not turned into a job', medical.length >= 1 && !claims.some((x) => x.status !== 'blocked' && /pill|pressure|පෙත්ත|ප්‍රෙෂර්/i.test(`${x.text_en} ${x.text_si}`)), report.privacy.medical.join(' | '));
    if (DATA) {
      const left = fs.readdirSync(DATA).filter((f) => f.startsWith('upload-'));
      const parts = fs.existsSync(path.join(DATA, 'uploads')) ? fs.readdirSync(path.join(DATA, 'uploads')) : [];
      const staging = path.join(DATA, 'households', HID, 'staging');
      check('privacy: nothing of the upload is left outside the home’s folder', left.length === 0 && parts.length === 0 && (!fs.existsSync(staging) || fs.readdirSync(staging).length === 0), `${left.length} temp, ${parts.length} parts`);
    }
    report.facts = claims.map((x) => ({ id: x.id, status: x.status, kind: x.kind, job: x.task_key, safety: x.safety, text_en: x.text_en, text_si: x.text_si, quote: x.quote, time: x.time, turn: x.turn_id, noun: x.object_noun || '', witnesses: Object.fromEntries((x.witnesses || []).map((w) => [w.name, w.status])), reason: x.blocked_reason || '' }));
    report.left_out = (c.left_out || []).map((x) => ({ reason: x.reason, text: x.text, start: x.start }));
    for (const f of report.facts) note(`[${f.status.padStart(12)}] ${String(f.time).padStart(5)} ${f.job.padEnd(18)} ${f.kind.padEnd(8)} ${f.text_en.slice(0, 70)} ${JSON.stringify(f.witnesses)}`);
  });

  // 4. Review: reword one, reject one, accept the rest --------------------------------------------
  let rejected = null;
  let edited = null;
  await stage('review', async () => {
    const open = claims.filter((x) => x.status === 'verified' || x.status === 'needs_review');
    rejected = open.find((x) => /come here first|මුලින්ම/i.test(`${x.text_en} ${x.quote}`)) || null;
    edited = open.find((x) => x !== rejected && /original|photocop|මුල් පිටපත්/i.test(`${x.text_en} ${x.quote}`)) || null;
    check('review: there are facts to review', open.length >= 6, `${open.length} waiting`);
    await page.goto(`${BASE}/h/${HID}/review`, { waitUntil: 'networkidle' });
    await page.waitForSelector('.claim');
    await shot(page, '04-review');
    if (edited) {
      const card = page.locator(`.claim[aria-labelledby="claim-${edited.id}"]`);
      await card.locator('.claim-actions .btn-quiet').click();
      const words = LANG === 'si' ? 'ගෙදර ඔප්පුවේ හෝ උප්පැන්න සහතිකවල මුල් පිටපත් කාටවත් දෙන්න එපා. ෆොටෝ කොපි දෙන්න.' : 'Never give the original deed or birth certificates to anyone. Give photocopies instead.';
      await card.locator(`.claim-edit textarea[lang="${LANG}"]`).fill(words);
      await card.locator('.claim-actions .btn-ok').click();
      await card.locator('.chip-lamp').waitFor({ timeout: 15000 }).catch(() => {});
      check('review: a reworded fact is marked as the owner’s own words', (await card.locator('.chip-lamp').count()) === 1);
      const after = (await api('/claims')).claims.find((x) => x.id === edited.id);
      check('review: the other language is marked as not yet translated', after && (after.untranslated || []).includes(LANG === 'si' ? 'en' : 'si'), JSON.stringify(after && { edited: after.edited, untranslated: after.untranslated }));
    }
    if (rejected) {
      const card = page.locator(`.claim[aria-labelledby="claim-${rejected.id}"]`);
      await card.locator('.claim-actions .btn:not(.btn-ok):not(.btn-quiet)').click();
      await page.waitForSelector(`.claim.claim-rejected[aria-labelledby="claim-${rejected.id}"]`, { timeout: 15000 });
      check('review: a fact can be rejected', true, rejected.text_en);
    } else check('review: the fact to reject was read', false, 'no “come here first” fact');
    for (const x of open) {
      if (x === rejected || x === edited) continue;
      const card = page.locator(`.claim[aria-labelledby="claim-${x.id}"]`);
      if (!(await card.count())) continue;
      await card.locator('.claim-actions .btn-ok').click();
      await page.waitForSelector(`.claim.claim-accepted[aria-labelledby="claim-${x.id}"]`, { timeout: 15000 }).catch(() => {});
    }
    claims = (await api('/claims')).claims;
    const acc = claims.filter((x) => x.status === 'accepted').length;
    check('review: the rest are accepted, the reworded one with them', acc === open.length - (rejected ? 1 : 0), `${acc} accepted of ${open.length}`);
    await page.locator('.tabs button').nth(1).click();
    await page.waitForSelector('.left-out-medical, .claim-blocked', { timeout: 5000 }).catch(() => {});
    const notUsed = await page.locator('main').innerText();
    check('review: “Not used” shows the medicine sentence, refused by code', (await page.locator('.left-out-medical').count()) >= 1);
    check('review: and shows nothing of the code', anySecret(notUsed).length === 0, anySecret(notUsed).join(','));
    await shot(page, '04-review-not-used');
  });

  // SAM 3.1 tracks each accepted object through its clip; the board then has every job.
  let board = null;
  let jobs = {};
  await stage('board', async () => {
    const t0 = Date.now();
    const objects = new Set(claims.filter((x) => x.status === 'accepted' && x.object_noun && x.mask).map((x) => `${x.recording_id}/${x.task_key}`));
    const tracked = await until(async () => {
      const ev = (await api('/evidence?limit=5000')).events.filter((e) => e.type === 'clip.tracked' || e.type === 'clip.track_failed');
      return ev.length >= objects.size ? ev : null;
    }, 900000, 4000);
    report.tracking = { objects: objects.size, seconds: Math.round((Date.now() - t0) / 1000), tracked: (tracked || []).filter((e) => e.type === 'clip.tracked').map((e) => ({ claim: e.payload.claim_id, frames: (e.payload.frames || []).length })), failed: (tracked || []).filter((e) => e.type === 'clip.track_failed').map((e) => e.payload) };
    check('board: SAM 3.1 tracked every accepted object through its clip', tracked && report.tracking.failed.length === 0 && report.tracking.tracked.length >= objects.size, `${report.tracking.tracked.length} of ${objects.size} in ${report.tracking.seconds} s`);
    board = await api('/board');
    for (const [k, re] of Object.entries(JOBS)) jobs[k] = board.tasks.find((t) => re.test(`${t.title_en} ${t.key} ${(t.object || {}).noun || ''}`) && !Object.values(jobs).includes(t)) || null;
    report.board = board.tasks.map((t) => ({ key: t.key, title_en: t.title_en, title_si: t.title_si, safety: t.safety, coverage: t.coverage, object: (t.object || {}).noun || null, clip: t.clip, points: t.points.length }));
    for (const t of report.board) note(`${t.key.padEnd(20)} ${t.title_en} / ${t.title_si}  object=${t.object} points=${t.points}`);
    check('board: the five jobs said in the walk-through are on the board', Object.values(jobs).every(Boolean), Object.entries(jobs).map(([k, t]) => `${k}=${t ? t.key : '-'}`).join(' '));
    check('board: each job has its title in both languages', board.tasks.every((t) => t.title_en && t.title_si));
    await page.goto(`${BASE}/h/${HID}`, { waitUntil: 'networkidle' });
    check('board: the page lists them', (await page.locator('.job-card').count()) === board.tasks.length, `${await page.locator('.job-card').count()} cards`);
    await shot(page, '05-board');
  });

  // The rejected words are silent in the job's clip; the accepted ones are heard.
  await stage('clip sound', async () => {
    const sw = jobs.switch;
    if (!sw || !rejected) throw new Error('no switch job or no rejected fact');
    const view = await api(`/recordings/${rec.id}?task=${sw.key}`);
    const clip = await download(`/media/${view.video}`, path.join(tmp, 'switch-clip.mp4'));
    const s = pcm(clip);
    const at = (turn) => [turn.start - view.video_start + 0.25, turn.end - view.video_start - 0.25];
    const accepted = new Set(claims.filter((x) => x.status === 'accepted').map((x) => x.turn_id));
    const inClip = rec.turns.filter((t) => t.start >= view.video_start - 0.05 && t.end <= view.video_start + s.length / 16000 + 0.05);
    const levels = inClip.map((t) => ({ turn: t.id, accepted: accepted.has(t.id), rms: Math.round(rms(s, ...at(t))) }));
    report.clip_sound = { job: sw.key, clip_start: view.video_start, seconds: Math.round((s.length / 16000) * 10) / 10, levels };
    const loud = levels.filter((l) => l.accepted).map((l) => l.rms);
    const quiet = levels.filter((l) => !l.accepted).map((l) => l.rms);
    check('clip: the words of the rejected fact are silent in the job’s clip', quiet.length >= 1 && Math.max(...quiet) < 30, JSON.stringify(levels));
    check('clip: the accepted facts are heard', loud.length >= 2 && Math.min(...loud) > 300, loud.join(','));
    // The owner changes her mind and accepts it after all: the clip is cut again, with those words.
    await page.goto(`${BASE}/h/${HID}/review?show=all`, { waitUntil: 'networkidle' });
    const card = page.locator(`.claim[aria-labelledby="claim-${rejected.id}"]`);
    await card.locator('.claim-actions .btn-quiet').nth(1).click();
    await page.waitForSelector(`.claim.claim-accepted[aria-labelledby="claim-${rejected.id}"]`, { timeout: 15000 });
    claims = (await api('/claims')).claims;
    const again = await api(`/recordings/${rec.id}?task=${sw.key}`);
    const clip2 = await download(`/media/${again.video}`, path.join(tmp, 'switch-clip-2.mp4'));
    const s2 = pcm(clip2);
    const back = rec.turns.find((t) => t.id === rejected.turn_id);
    const level = Math.round(rms(s2, back.start - again.video_start + 0.25, back.end - again.video_start - 0.25));
    report.clip_sound.after_undo = { clip_changed: again.video !== view.video, rms: level };
    check('clip: undone, the clip is cut again and those words are heard', again.video !== view.video && level > 300, `rms ${level}`);
  });

  // 5. Prove -------------------------------------------------------------------------------------
  const ruwan = () => board.people.find((p) => p.name === T.people[0].name);
  async function proveShow(task, file, label) {
    await page.goto(`${BASE}/h/${HID}/prove?person=${ruwan().id}&task=${task.key}`, { waitUntil: 'networkidle' });
    await page.waitForSelector('.proof-card');
    const resp = page.waitForResponse((r) => r.url().includes('/proofs/show'), { timeout: 180000 });
    const t0 = Date.now();
    await page.setInputFiles('.proof-card input[type=file][accept="image/*"]', file);
    const r = await resp;
    const body = await r.json().catch(() => ({}));
    await page.waitForSelector('.proof-card .verdict, .toast-bad', { timeout: 20000 }).catch(() => {});
    const shown = (await page.locator('.proof-card .verdict').count()) ? await page.locator('.proof-card .verdict').first().innerText() : (await page.locator('.toast-bad').count()) ? await page.locator('.toast-bad').last().innerText() : '';
    const out = { label, status: r.status(), outcome: body.outcome || (body.error ? `refused:${body.error}` : null), passed: body.passed, reasons: body.reasons_en || body.detail || body.message || null, seconds: Math.round((Date.now() - t0) / 100) / 10, shown: shown.slice(0, 200), matched: body.evidence && body.evidence.matched, mismatches: body.evidence && body.evidence.mismatches, confidence: body.evidence && body.evidence.confidence };
    (report.proofs = report.proofs || []).push({ kind: 'show', job: task.key, ...out });
    note(`show ${label}: ${out.status} ${out.outcome} ${JSON.stringify(out.reasons).slice(0, 160)}`);
    return out;
  }
  async function proveTell(task, text, label, lang = LANG) {
    await page.goto(`${BASE}/h/${HID}/prove?person=${ruwan().id}&task=${task.key}`, { waitUntil: 'networkidle' });
    const card = page.locator('.proof-card').last();
    await card.locator(`.seg button[lang="${lang}"]`).click();
    await card.locator('.proof-actions .btn:not(.btn-primary):not(.btn-danger)').click();
    await card.locator('.tell-form textarea').fill(text);
    const resp = page.waitForResponse((r) => r.url().includes('/proofs/tell'), { timeout: 180000 });
    const t0 = Date.now();
    await card.locator('.tell-form button[type=submit]').click();
    const r = await resp;
    const body = await r.json().catch(() => ({}));
    await page.waitForSelector('.proof-card .verdict, .toast-bad', { timeout: 20000 }).catch(() => {});
    const out = { label, status: r.status(), passed: body.passed, code: body.error || null, reasons: body.reasons_en || body.detail || null, points: ((body.evidence || {}).points || []).map((p) => ({ text: p.text_en, safety: p.safety, said: p.covered, quoted: p.verified, quote: p.quote })), seconds: Math.round((Date.now() - t0) / 100) / 10 };
    (report.proofs = report.proofs || []).push({ kind: 'tell', job: task.key, answer: text, ...out });
    note(`tell ${label}: ${out.status} passed=${out.passed} ${out.code || ''} ${JSON.stringify(out.reasons).slice(0, 160)}`);
    return out;
  }

  await stage('prove', async () => {
    const lock = jobs.padlock;
    if (!lock || !lock.object) throw new Error('no padlock job with an object');
    // The app's own picture of the padlock, saved again the way a phone saves a screenshot.
    const still = await download(`/media/${lock.object.keyframe_path}`, path.join(tmp, 'still.jpg'));
    const screenshot = path.join(tmp, 'saved-from-the-app.jpg');
    execFileSync('ffmpeg', ['-v', 'error', '-y', '-i', still, '-vf', 'scale=iw*0.9:-2', '-q:v', '6', screenshot]);
    const copy = await proveShow(lock, screenshot, 'the app’s own picture, saved again');
    check('show me: the app’s own picture is refused as not a new photo', copy.status >= 400 && /not_new/.test(copy.outcome || ''), `${copy.status} ${copy.outcome}`);
    const other = await proveShow(lock, path.join(PHOTOS, 'met-463365-0.jpg'), 'a different padlock');
    check('show me: a different padlock does not pass', other.status === 200 && other.passed === false, `${other.outcome}: ${JSON.stringify(other.reasons).slice(0, 120)}`);
    // From the side and above: the held-out photos show the app can't confirm this view. It must
    // not be called a different padlock; asking for another photo is the right answer.
    const side = await proveShow(lock, path.join(PHOTOS, 'met-468867-3.jpg'), 'the same padlock from the side, hard to tell');
    check('show me: a hard view of the same padlock is not called a different one', side.status === 200 && side.outcome !== 'mismatch' && side.passed !== undefined, `${side.outcome}: ${JSON.stringify(side.reasons).slice(0, 140)}`);
    // The family's own new photo of the clock in the hall: another photograph of it from the front,
    // in other light (the Met's 14298-2; the walk-through filmed 14298-0).
    const clock = jobs.clock;
    if (!clock || !clock.object) throw new Error('no clock job with an object');
    const same = await proveShow(clock, path.join(PHOTOS, 'met-14298-2.jpg'), 'a new photo of the same clock');
    check('show me: a new photo of the same clock passes', same.status === 200 && same.passed === true, `${same.outcome}: ${JSON.stringify(same.reasons).slice(0, 160)}`);
    if (same.passed) check('show me: SAM 3.1’s outline is drawn on the photo', (await page.locator('.proof-photo .mask-svg').count()) === 1);
    await shot(page, '06-show');

    const pump = jobs.pump;
    const good = await proveTell(pump, T.tellGood, 'every point');
    check('tell me: an explanation with every point passes', good.status === 200 && good.passed === true, JSON.stringify(good.reasons).slice(0, 160));
    const missing = await proveTell(pump, T.tellMissing, 'the safety step left out');
    check('tell me: leaving out the safety step does not pass', missing.status === 200 && missing.passed === false, JSON.stringify(missing.reasons).slice(0, 160));
    const pasted = pump.points.map((p) => (LANG === 'si' && p.text_si ? p.text_si : p.text_en)).join(' ');
    const copied = await proveTell(pump, pasted, 'the steps pasted back');
    check('tell me: the steps pasted back are refused', copied.status >= 400 && copied.code === 'copied', `${copied.status} ${copied.code}`);
    await shot(page, '06-tell');
  });

  // A spoken explanation, and a spoken question, through the browser's microphone.
  async function withMicrophone(text, fn, recording = '') {
    const wav = path.join(tmp, `mic-${Date.now()}.wav`);
    let seconds;
    if (recording) {
      // A real recording, padded with a little silence, in the fake microphone's format.
      execFileSync('ffmpeg', ['-v', 'error', '-y', '-i', recording, '-af', 'adelay=600|600,apad=pad_dur=1.2', '-ar', '48000', '-ac', '1', '-c:a', 'pcm_s16le', wav]);
      seconds = Number(execFileSync('ffprobe', ['-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', wav]).toString());
    } else seconds = speak(text, wav);
    const b = await chromium.launch({ args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', `--use-file-for-fake-audio-capture=${wav}%noloop`] });
    const ctx = await b.newContext({ viewport: { width: 390, height: 844 }, reducedMotion: 'reduce', permissions: ['microphone'] });
    await ctx.addInitScript(([lang, hid, token]) => {
      try {
        localStorage.setItem('iid.lang', lang);
        localStorage.setItem('iid.tokens', JSON.stringify({ [hid]: token }));
      } catch (e) {}
    }, [LANG, HID, OWNER]);
    const p = await ctx.newPage();
    p.on('pageerror', (e) => errors.push(`pageerror, microphone: ${e}`));
    try {
      return await fn(p, seconds);
    } finally {
      await b.close();
    }
  }

  await stage('prove by voice', async () => {
    const sw = jobs.switch;
    const out = await withMicrophone(T.tellVoice, async (p, seconds) => {
      await p.goto(`${BASE}/h/${HID}/prove?person=${ruwan().id}&task=${sw.key}`, { waitUntil: 'networkidle' });
      const card = p.locator('.proof-card').last();
      await card.locator(`.seg button[lang="${LANG}"]`).click();
      await card.locator('.proof-actions .btn-primary').click();
      await card.locator('.proof-actions .btn-danger').waitFor({ timeout: 10000 });
      await sleep((seconds + 0.8) * 1000);
      const resp = p.waitForResponse((r) => r.url().includes('/proofs/tell'), { timeout: 180000 });
      await card.locator('.proof-actions .btn-danger').click();
      const r = await resp;
      const body = await r.json().catch(() => ({}));
      await p.waitForSelector('.proof-card .verdict, .toast-bad', { timeout: 20000 }).catch(() => {});
      await shot(p, '07-tell-voice');
      return { status: r.status(), passed: body.passed, code: body.error || null, transcript: (body.evidence || {}).transcript || '', reasons: body.reasons_en || body.detail, points: ((body.evidence || {}).points || []).map((p) => ({ text: p.text_en, safety: p.safety, said: p.covered, quoted: p.verified, quote: p.quote })) };
    });
    (report.proofs = report.proofs || []).push({ kind: 'tell (spoken)', job: sw.key, said: T.tellVoice, ...out });
    note(`spoken: ${out.status} passed=${out.passed} ${out.code || ''} heard “${out.transcript}”`);
    if (TELL_VOICE_EXPECT === 'unclear') {
      check('tell me by voice: words the speech model can’t make out are not judged; it asks again', out.status === 400 && out.code === 'unclear', `${out.status} ${out.code} ${JSON.stringify(out.reasons).slice(0, 100)}`);
    } else {
      check('tell me by voice: the spoken explanation is heard', out.status === 200 && out.transcript.length > 20, out.transcript.slice(0, 120));
      check('tell me by voice: and passes', out.passed === true, JSON.stringify(out.reasons).slice(0, 160));
    }
  });

  // 6. Help ------------------------------------------------------------------------------------
  await stage('help', async () => {
    await page.goto(`${BASE}/h/${HID}/help`, { waitUntil: 'networkidle' });
    report.help = [];
    for (const a of T.ask) {
      await page.fill('#ask', a.q);
      const resp = page.waitForResponse((r) => new URL(r.url()).pathname.endsWith('/help'), { timeout: 120000 });
      const t0 = Date.now();
      await page.locator('form.ask button[type=submit]').click();
      const r = await resp;
      const body = await r.json().catch(() => ({}));
      await page.waitForSelector('.asked .answer', { timeout: 15000 }).catch(() => {});
      const kind = (await page.locator('.asked .answer-emergency').count()) ? 'emergency' : (await page.locator('.asked .answer-medical').count()) ? 'medical' : (await page.locator('.asked .answer-none').count()) ? 'none' : (await page.locator('.asked .answer').count()) ? 'job' : 'nothing';
      const task = board.tasks.find((t) => t.key === body.task_key);
      const ok = kind === a.expect && (a.expect !== 'job' || (task && task.key === (jobs[a.job] || {}).key));
      const shownQ = (await page.locator('.asked-q').count()) ? await page.locator('.asked-q').innerText() : '';
      report.help.push({ q: a.q, expect: a.expect, job: a.job || null, got: kind, task: task ? task.key : null, decided_by: body.decided_by, seconds: Math.round((Date.now() - t0) / 100) / 10, shown_question: shownQ });
      check(`help: “${a.q}” → ${a.expect}${a.job ? ` (${a.job})` : ''}`, ok, `${kind} ${task ? task.key : ''} ${body.decided_by || ''}`);
      if (a.secret) {
        check('help: the PIN in the question is shown back hidden', !shownQ.includes(a.secret) && shownQ.includes('[hidden]'), shownQ.slice(0, 80));
        const kept = anySecret(JSON.stringify((await api('/evidence?limit=5000')).events)).filter((f) => f === a.secret);
        check('help: and is not kept anywhere in the log', kept.length === 0);
      }
    }
    await shot(page, '08-help');
    // The WhatsApp preview: a power cut asked in Sinhala, then a question in the run's language.
    await page.fill('#wa-text', 'කරන්ට් ගියා, මොකද කරන්නේ?');
    await page.locator('.wa-input button[type=submit]').click();
    await page.waitForSelector('.wa-them:not(.wa-typing)', { timeout: 120000 });
    const first = await page.locator('.wa-them:not(.wa-typing)').first().innerText();
    await page.fill('#wa-text', T.whatsapp);
    await page.locator('.wa-input button[type=submit]').click();
    await page.waitForFunction((n) => document.querySelectorAll('.wa-me').length >= 2 && !document.querySelector('.wa-typing') && document.querySelectorAll('.wa-them').length >= n, 2, { timeout: 120000 }).catch(() => {});
    const replies = await page.locator('.wa-them:not(.wa-typing)').allInnerTexts();
    const answered = (await api('/evidence?limit=5000')).events.filter((e) => e.type === 'help.answered').slice(-2);
    report.whatsapp = replies.map((r, i) => ({ reply: unlink(r).slice(0, 400), decided_by: (answered[i] || {}).payload && answered[i].payload.decided_by, reason: (answered[i] || {}).payload && answered[i].payload.reason }));
    const sw = jobs.switch;
    check('whatsapp: a power cut asked in Sinhala gets the main switch steps, in Sinhala', first.includes(sw.title_si) && first.includes('කියපු විදිහ'), first.slice(0, 120));
    check('whatsapp: a typed question gets the padlock job', replies.length >= 2 && (replies[replies.length - 1].includes(jobs.padlock.title_en) || replies[replies.length - 1].includes(jobs.padlock.title_si)), (replies[replies.length - 1] || '').slice(0, 120));
    await shot(page, '08-whatsapp');
  });

  await stage('help by voice', async () => {
    const said = HELP_VOICE_WAV ? HELP_VOICE_SAID : T.helpVoice;
    const out = await withMicrophone(said, async (p, seconds) => {
      await p.goto(`${BASE}/h/${HID}/help`, { waitUntil: 'networkidle' });
      await p.locator('form.ask button[type=button]').click();
      await p.locator('form.ask button.btn-danger').waitFor({ timeout: 10000 });
      await sleep((seconds + 0.8) * 1000);
      const resp = p.waitForResponse((r) => r.url().includes('/help/voice'), { timeout: 180000 });
      await p.locator('form.ask button.btn-danger').click();
      const r = await resp;
      const body = await r.json().catch(() => ({}));
      await p.waitForSelector('.asked .answer', { timeout: 15000 }).catch(() => {});
      await shot(p, '08-help-voice');
      return { status: r.status(), question: body.question || '', task: body.task_key || null, decided_by: body.decided_by, code: body.error || null };
    }, HELP_VOICE_WAV);
    report.help_voice = { said, voice: HELP_VOICE_WAV ? `recording ${path.basename(HELP_VOICE_WAV)}` : 'eSpeak NG', ...out, cer: cer(said, out.question) };
    note(`asked by voice: heard “${out.question}” → ${out.task} (character error rate ${report.help_voice.cer}%)`);
    check('help by voice: the question is heard', out.status === 200 && out.question.length > 8, out.question);
    if (LANG === 'si') check('help by voice: heard in Sinhala letters', /[\u0D80-\u0DFF]/.test(out.question) && !/[a-z]{4,}/i.test(out.question), out.question);
    if (HELP_VOICE_WAV) {
      // A real recording that isn't about the house: the line must say so, not pick a job.
      check('help by voice: a question about nothing recorded is answered honestly', out.task === null, `${out.task} ${out.decided_by || ''}`);
    } else check('help by voice: and answered with the water pump', out.task === (jobs.pump || {}).key, `${out.task} ${out.decided_by || ''}`);
  });

  // A gap question answered by voice (the API offers it; the board's form is typed): the answer
  // is heard, read into facts and checked like the walk-through, and waits for review.
  await stage('gap by voice', async () => {
    const gaps = (await api('/board')).gaps || [];
    report.gap_voice = { gaps: gaps.map((g) => ({ task: g.task_key, slot: g.slot, q: g.question_en })) };
    const gap = gaps.find((g) => g.task_key === (jobs.pump || {}).key) || gaps[0];
    if (!gap) {
      check('gap by voice: there is a question to answer', false, 'no gaps on the board');
      return;
    }
    const said = LANG === 'si' ? 'ඒක ලොකු සද්දයක් දානවා නම් ඒක ඕෆ් කරලා සුනිල් මාමට කතා කරන්න.' : 'If it makes a loud grinding noise, switch it off at once and call Sunil, the plumber.';
    const wav = path.join(tmp, 'gap.wav');
    speak(said, wav);
    const form = new FormData();
    form.set('task_key', gap.task_key);
    form.set('slot', gap.slot);
    form.set('lang', LANG);
    form.set('audio', new Blob([fs.readFileSync(wav)], { type: 'audio/wav' }), 'answer.wav');
    const t0 = Date.now();
    const res = await fetch(`${BASE}/api/h/${HID}/gaps/answer`, { method: 'POST', headers: { Authorization: `Bearer ${OWNER}` }, body: form });
    const body = await res.json().catch(() => ({}));
    const after = (await api('/claims')).claims.filter((c) => c.recording_id === body.recording_id);
    report.gap_voice = { ...report.gap_voice, asked: gap.question_en, said, status: res.status, error: body.error || null, seconds: Math.round((Date.now() - t0) / 100) / 10, facts: after.map((c) => ({ text_en: c.text_en, text_si: c.text_si, status: c.status, job: c.task_key })) };
    note(`gap “${gap.question_en}” answered by voice: ${res.status} ${body.error || ''} → ${after.map((c) => `[${c.status}] ${c.text_en}`).join(' | ')}`);
    if (TELL_VOICE_EXPECT === 'unclear') {
      check('gap by voice: words the speech model can’t make out are refused, not read', res.status === 400 && body.error === 'unclear', `${res.status} ${body.error}`);
    } else {
      check('gap by voice: the spoken answer becomes facts for that job', res.ok && after.length >= 1 && after.every((c) => c.task_key === gap.task_key), `${res.status} ${after.length} facts`);
      check('gap by voice: and they wait for the owner’s review, checked', after.every((c) => ['verified', 'needs_review'].includes(c.status)), after.map((c) => c.status).join(','));
    }
  });

  // 7. The family's links ------------------------------------------------------------------------
  let links = null;
  await stage('links', async () => {
    links = await api('/links');
    const sticker = links.stickers.find((s) => s.task_key === jobs.switch.key);
    const fresh = await browser.newContext({ viewport: { width: 390, height: 844 }, reducedMotion: 'reduce' });
    const fp = await fresh.newPage();
    fp.on('pageerror', (e) => errors.push(`pageerror, sticker: ${e}`));
    await fp.goto(`${BASE}${new URL(sticker.url).pathname}`, { waitUntil: 'domcontentloaded' });
    await fp.waitForSelector('.sticker-main h1', { timeout: 20000 });
    await fp.waitForSelector('.sticker-main video', { timeout: 20000 }).catch(() => {});
    const sources = await fp.locator('.sticker-main video source').evaluateAll((els) => els.map((e) => e.getAttribute('src') || ''));
    check('sticker: its clip is the job’s own cut', sources.length >= 1 && sources.every((x) => x.includes(`/jobs/${jobs.switch.key}-`)), sources.map((x) => x.split('/').pop().split('?')[0]).join(' '));
    await fp.locator('.sticker-main .clip-play').click().catch(() => {});
    await fp.waitForFunction(() => {
      const v = document.querySelector('.sticker-main video');
      return !!v && v.readyState >= 2 && v.currentTime > 1.5;
    }, null, { timeout: 40000 }).catch(() => {});
    const played = await fp.evaluate(() => {
      const v = document.querySelector('.sticker-main video');
      return v ? { t: Math.round(v.currentTime * 10) / 10, error: v.error ? v.error.code : null } : null;
    });
    check('sticker: on a phone that never opened the home, the clip plays', played && played.t >= 1.5 && played.error === null, JSON.stringify(played));
    check('sticker: with SAM 3.1’s outline drawn over it', (await fp.locator('.sticker-main .clip-stage .mask-svg').count()) >= 1);
    await shot(fp, '09-sticker');
    await fresh.close();
    const otherStill = jobs.padlock.object && jobs.padlock.object.keyframe_path;
    const r1 = await api(`/media/${otherStill}`, { token: sticker.token, raw: true });
    check('sticker: cannot open another job’s picture', r1.status === 403, String(r1.status));
    const r2 = await api(`/media/${rec.video}`, { token: sticker.token, raw: true });
    check('sticker: cannot open the whole walk-through', r2.status === 403, String(r2.status));
    const person = links.people.find((p) => p.name === T.people[0].name);
    const r3 = await api('/evidence', { token: person.token, raw: true });
    check('person link: cannot open the log', r3.status === 403, String(r3.status));
    const r4 = await api(`/media/${rec.video}`, { token: person.token, raw: true });
    check('person link: cannot open the whole walk-through, with every word said', r4.status === 403, String(r4.status));
    const r5 = await api(`/recordings/${rec.id}`, { token: person.token, raw: true });
    check('person link: cannot open the recording itself, transcript and all', r5.status === 403, String(r5.status));
    const r6 = await api(`/recordings/${rec.id}?task=${jobs.switch.key}`, { token: person.token, raw: true });
    const view = r6.ok ? await r6.json() : {};
    check('person link: a job shows its own clip, with no transcript', r6.ok && view.scoped === true && (view.turns || []).length === 0 && String(view.video || '').includes('/jobs/'), `${r6.status} ${(view.turns || []).length} turns`);
    // Removing a person: her link stops at once, and her phone lets go of the home.
    const dilini = links.people.find((p) => p.name === T.people[1].name);
    const kctx = await browser.newContext({ viewport: { width: 390, height: 844 }, reducedMotion: 'reduce' });
    const kp = await kctx.newPage();
    await kp.goto(`${BASE}${new URL(dilini.url).pathname}`, { waitUntil: 'domcontentloaded' });
    await kp.waitForSelector('.board-hero', { timeout: 15000 });
    await page.goto(`${BASE}/h/${HID}/people`, { waitUntil: 'networkidle' });
    const row = page.locator('.person-row', { hasText: T.people[1].name });
    await row.locator('.icon-btn').click();
    await row.locator('.person-edit .btn-quiet').click();
    await page.waitForFunction((name) => ![...document.querySelectorAll('.person-row')].some((r) => r.textContent.includes(name)), T.people[1].name, { timeout: 15000 });
    await kp.reload({ waitUntil: 'domcontentloaded' });
    await kp.waitForSelector('.center-page .state', { timeout: 15000 }).catch(() => {});
    check('removed: her link stops working at once', (await kp.locator('.center-page .state').count()) === 1);
    check('removed: and her phone lets go of the home', await kp.evaluate((id) => !JSON.parse(localStorage.getItem('iid.tokens') || '{}')[id], HID));
    await kctx.close();
    // Replacing every link: an old sticker stops working, the owner carries on.
    await page.goto(`${BASE}/h/${HID}/card?tab=links`, { waitUntil: 'networkidle' });
    await page.locator('.danger-zone > .btn').click();
    await page.locator('.danger-zone .btn-danger').click();
    await sleep(800);
    const sctx = await browser.newContext({ viewport: { width: 390, height: 844 } });
    const sp = await sctx.newPage();
    await sp.goto(`${BASE}${new URL(sticker.url).pathname}`, { waitUntil: 'domcontentloaded' });
    await sp.waitForSelector('.center-page .state', { timeout: 15000 }).catch(() => {});
    check('replaced: an old sticker stops working', (await sp.locator('.center-page .state').count()) === 1);
    await sctx.close();
    OWNER = await page.evaluate((id) => JSON.parse(localStorage.getItem('iid.tokens'))[id], HID);
    await page.goto(`${BASE}/h/${HID}`, { waitUntil: 'networkidle' });
    check('replaced: the owner carries on with the new link', (await page.locator('.board-hero').count()) === 1);
    links = await api('/links');
  });

  // 8. Offline, with the server out of reach --------------------------------------------------------
  await stage('offline', async () => {
    const relay = await startRelay(new URL(BASE));
    const octx = await browser.newContext({ viewport: { width: 390, height: 844 }, reducedMotion: 'reduce' });
    await octx.addInitScript(([lang, hid, token]) => {
      try {
        localStorage.setItem('iid.lang', lang);
        if (!localStorage.getItem('iid.tokens')) localStorage.setItem('iid.tokens', JSON.stringify({ [hid]: token }));
      } catch (e) {}
    }, [LANG, HID, OWNER]);
    const op = await octx.newPage();
    op.on('pageerror', (e) => errors.push(`pageerror, offline: ${e}`));
    await op.goto(`${relay.base}/h/${HID}/card?tab=offline`, { waitUntil: 'networkidle' });
    await op.evaluate(() => navigator.serviceWorker && navigator.serviceWorker.ready);
    await op.reload({ waitUntil: 'networkidle' });
    const t0 = Date.now();
    await op.locator('.offline-actions .btn-primary').click();
    await op.waitForSelector('.offline .ok-note, .offline .warn-note', { timeout: 180000 });
    const saved = await op.evaluate((id) => JSON.parse(localStorage.getItem(`iid.offline.${id}`) || 'null'), HID);
    report.offline = { seconds: Math.round((Date.now() - t0) / 100) / 10, saved };
    check('offline: the whole home is saved on this phone', (await op.locator('.offline .ok-note').count()) === 1 && saved && saved.failed === 0, JSON.stringify(saved));
    await relay.close();
    await octx.setOffline(true);
    check('offline: the server really is out of reach', !(await reachable(`${relay.base}/api/health`)));
    await op.goto(`${relay.base}/h/${HID}`, { waitUntil: 'domcontentloaded' }).catch(() => {});
    await op.waitForSelector('.board-hero', { timeout: 15000 }).catch(() => {});
    check('offline: the board opens', (await op.locator('.board-hero').count()) === 1 && (await op.locator('.offline-bar').count()) === 1);
    const st = links.stickers.find((s) => s.task_key === jobs.pump.key);
    await op.goto(`${relay.base}${new URL(st.url).pathname}`, { waitUntil: 'domcontentloaded' }).catch(() => {});
    await op.waitForSelector('.sticker-main h1', { timeout: 15000 }).catch(() => {});
    check('offline: a sticker opens its job from the saved copy', (await op.locator('.sticker-main h1').count()) === 1);
    await op.waitForSelector('.sticker-main figure.clip', { timeout: 15000 }).catch(() => {});
    check('offline: with its clip', (await op.locator('.sticker-main figure.clip').count()) === 1);
    await shot(op, '10-offline-sticker');
    await octx.close();
  });

  // 9. What it cost, the log, and deleting the home ----------------------------------------------------
  await stage('log and delete', async () => {
    const ev = await api('/evidence?limit=5000');
    report.log = { events: ev.count, chain_ok: ev.chain_ok, broken_at: ev.broken_at };
    check('log: every change is in the hash chain, and it is intact', ev.chain_ok === true, `${ev.count} events`);
    report.cost = costs(ev.events);
    note(`models cost $${report.cost.total_usd.toFixed(4)}`);
    for (const [k, v] of Object.entries(report.cost.by_purpose)) note(`  ${k.padEnd(44)} ${String(v.calls).padStart(3)} calls  $${v.usd.toFixed(4)}`);
    await page.goto(`${BASE}/h/${HID}/evidence`, { waitUntil: 'networkidle' });
    check('evidence page: shows the chain as intact', (await page.locator('.chain').count()) === 1);
    await page.goto(`${BASE}/h/${HID}/people`, { waitUntil: 'networkidle' });
    await page.locator('.danger-zone input').fill('DELETE');
    await page.locator('.danger-zone button.btn-danger').click();
    await page.waitForURL(`${BASE}/`, { timeout: 20000 });
    const gone = await api('/board', { raw: true });
    check('delete: the home is gone', gone.status === 401 || gone.status === 404, String(gone.status));
    report.deleted = true;
    if (DATA) {
      const rest = [];
      const walkDir = (d) => {
        for (const f of fs.readdirSync(d, { withFileTypes: true })) {
          const p = path.join(d, f.name);
          if (p.includes(HID)) rest.push(path.relative(DATA, p));
          if (f.isDirectory()) walkDir(p);
        }
      };
      walkDir(DATA);
      check('delete: nothing of it is left in the server’s data folder', rest.length === 0, rest.slice(0, 5).join(', '));
    }
  });

  check('no script errors on any page', errors.length === 0, errors.slice(0, 4).join(' | '));
  await browser.close();
  fs.rmSync(tmp, { recursive: true, force: true });
  report.result = failed ? 'failed' : 'passed';
  report.passed = report.checks.filter((c) => c.ok).length;
  report.failed = failed;
  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  fs.writeFileSync(OUT, JSON.stringify(report, null, 1));
  console.log(`\n${report.passed} passed, ${failed} failed; report: ${path.relative(ROOT, OUT)}`);
  process.exit(failed ? 1 : 0);
})().catch((err) => {
  console.error(err && err.message ? err.message : err);
  try {
    report.result = 'error';
    report.error = String(err && err.message ? err.message : err).slice(0, 500);
    fs.writeFileSync(OUT, JSON.stringify(report, null, 1));
  } catch (e) {}
  process.exit(2);
});
