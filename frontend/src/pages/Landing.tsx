import {
  BadgeCheck,
  BookOpenCheck,
  CircleCheck,
  CircleX,
  EyeOff,
  GraduationCap,
  Languages,
  Lock,
  MessageCircle,
  Mic,
  QrCode,
  Quote,
  ScanEye,
  ShieldCheck,
  Sparkles,
  Trash2,
  Video,
  WifiOff,
  Zap,
} from 'lucide-react';
import type { CSSProperties } from 'react';
import { Logo } from '../components/Logo';
import { MaskOverlay } from '../components/MaskOverlay';
import { LangToggle } from '../components/Shell';
import { format, useI18n } from '../i18n';
import { lastHousehold } from '../lib/api';
import { useHealth } from '../lib/health';
import { number } from '../lib/format';
import { landingShapes, type LandingShape } from '../lib/landingShapes';
import { Link } from '../lib/router';

const SOURCE_URL = (import.meta.env.VITE_SOURCE_URL as string | undefined) || '';

/** Where the pin sits, as a fraction of the frame: the middle of the mask (worked out when the
    images are built), or else the centre of the outline's points. */
function anchor(shape: LandingShape): [number, number] {
  if (shape.anchor) return shape.anchor;
  const nums = shape.d.match(/-?\d+(\.\d+)?/g)?.map(Number) ?? [];
  let x = 0;
  let y = 0;
  let n = 0;
  for (let i = 0; i + 1 < nums.length; i += 2) {
    x += nums[i];
    y += nums[i + 1];
    n += 1;
  }
  return n ? [x / n / shape.w, y / n / shape.h] : [0.5, 0.5];
}

const PINS = [
  { key: 'breaker', title: 'pinSwitch', by: 'pinSwitchBy', state: 'ok' as const, nudge: [0.02, -0.02] },
  { key: 'pump', title: 'pinPump', by: 'pinPumpBy', state: 'risk' as const, nudge: [0.04, 0.06] },
  { key: 'documents', title: 'pinDocs', by: 'pinDocsBy', state: 'ok' as const, nudge: [0, 0] },
];

function PinCard({ name, title, by, state, delay, nudge }: { name: string; title: string; by: string; state: 'ok' | 'risk'; delay: number; nudge: number[] }) {
  const shape = landingShapes[name];
  const [ax, ay] = anchor(shape);
  const pos = { left: `${Math.min(80, Math.max(16, (ax + nudge[0]) * 100))}%`, top: `${Math.min(78, Math.max(18, (ay + nudge[1]) * 100))}%` } as CSSProperties;
  return (
    <figure className="pin-card" style={{ ['--delay' as string]: `${delay}ms` } as CSSProperties}>
      <img src={`/images/pin-${name}-480.webp`} srcSet={`/images/pin-${name}-480.webp 480w, /images/pin-${name}-960.webp 960w`} sizes="(max-width: 700px) 78vw, 360px" alt="" width={480} height={360} loading="eager" />
      <MaskOverlay d={shape.d} width={shape.w} height={shape.h} trace delay={delay} />
      <span className="pin-dot" style={pos} aria-hidden />
      <figcaption className={`pin-label pin-label-${state}`}>
        <strong>{title}</strong>
        <span>
          {state === 'ok' ? <CircleCheck aria-hidden /> : <GraduationCap aria-hidden />}
          {by}
        </span>
      </figcaption>
    </figure>
  );
}

const PREVIEW = [
  { en: 'Gas cylinder', si: 'ගෑස් සිලින්ඩරය', c: 'uncovered' },
  { en: 'Electricity bill', si: 'විදුලි බිල', c: 'uncovered' },
  { en: 'Nethum extra class', si: 'නෙතුම් අමතර පන්තිය', c: 'uncovered' },
  { en: 'Water pump', si: 'වතුර පොම්පය', c: 'at_risk' },
  { en: 'Main switch box', si: 'ප්‍රධාන ස්විච් පෙට්ටිය', c: 'covered' },
  { en: 'Important documents', si: 'වැදගත් ලියකියවිලි', c: 'covered' },
] as const;

export function Landing() {
  const { d, lang } = useI18n();
  const l = d.landing;
  const resume = lastHousehold();
  const live = useHealth()?.mode === 'live';
  const docs = landingShapes.documents;
  const proof = landingShapes.proofRight;

  return (
    <div className="landing">
      <a href="#main" className="skip-link">
        {l.skip}
      </a>
      <header className="l-header">
        <Link to="/" className="l-brand" aria-label="If I Disappear">
          <Logo light size={34} />
        </Link>
        <nav className="l-nav" aria-label={d.nav.main}>
          <a href="#how">{l.navHow}</a>
          <a href="#proof">{l.navProof}</a>
          <a href="#privacy">{l.navPrivacy}</a>
          <a href="#meta">{l.navMeta}</a>
        </nav>
        <div className="l-header-end">
          <LangToggle dark />
          <Link to={resume ? `/h/${resume}` : '/try'} className="btn btn-primary btn-sm l-header-cta">
            {resume ? l.resume : l.heroCtaShort}
          </Link>
        </div>
      </header>

      <main id="main">
        <section className="l-hero" aria-labelledby="hero-title">
          <picture className="l-hero-bg">
            <source media="(max-width: 700px)" srcSet="/images/hero-portrait-810.webp" />
            <img src="/images/hero-1920.webp" srcSet="/images/hero-800.webp 800w, /images/hero-1280.webp 1280w, /images/hero-1920.webp 1920w" sizes="100vw" alt="" fetchPriority="high" />
          </picture>
          <div className="l-hero-copy">
            <p className="l-hero-line">{l.heroLine}</p>
            <h1 id="hero-title">{l.heroTitle}</h1>
            <p className="l-hero-sub">{l.heroSub}</p>
            <div className="l-hero-ctas">
              <Link to="/try" className="btn btn-primary">
                {l.heroCta}
              </Link>
              <a href="#how" className="btn btn-ghost-dark">
                {l.heroCta2}
              </a>
            </div>
            <p className="l-hero-note">{l.heroNote}</p>
            {live && (
              <p className="l-hero-note">
                <Link to="/start" className="l-start-link">
                  {l.startOwn}
                </Link>
              </p>
            )}
          </div>
          <div className="l-pins" role="list" aria-label={l.pinsLabel} tabIndex={0}>
            {PINS.map((p, i) => (
              <div role="listitem" key={p.key}>
                <PinCard name={p.key} title={l[p.title as 'pinSwitch']} by={l[p.by as 'pinSwitchBy']} state={p.state} delay={350 + i * 260} nudge={p.nudge} />
              </div>
            ))}
          </div>
        </section>

        <section className="l-stats" aria-label={l.statsLabel}>
          <div className="l-wrap l-stats-grid">
            <div className="l-stat">
              <p className="l-stat-n">{number(212302, lang)}</p>
              <p>{l.statA}</p>
            </div>
            <div className="l-stat">
              <p className="l-stat-n">{number(82050, lang)}</p>
              <p>{l.statB}</p>
            </div>
            <div className="l-stat-say">
              <p>{l.statC}</p>
              <p className="l-source">{l.statSource}</p>
            </div>
          </div>
        </section>

        <section id="how" className="l-section l-how" aria-labelledby="how-title">
          <div className="l-wrap">
            <h2 id="how-title" className="l-h2">
              {l.howTitle}
            </h2>
            <ol className="l-steps">
              <li>
                <span className="l-step-icon" aria-hidden>
                  <Video />
                </span>
                <h3>{l.how1}</h3>
                <p>{l.how1Body}</p>
              </li>
              <li>
                <span className="l-step-icon" aria-hidden>
                  <ShieldCheck />
                </span>
                <h3>{l.how2}</h3>
                <p>{l.how2Body}</p>
              </li>
              <li>
                <span className="l-step-icon" aria-hidden>
                  <BadgeCheck />
                </span>
                <h3>{l.how3}</h3>
                <p>{l.how3Body}</p>
              </li>
            </ol>
          </div>
        </section>

        <section id="witnesses" className="l-section l-witness" aria-labelledby="wit-title">
          <div className="l-wrap l-split">
            <figure className="l-evidence">
              <div className="l-evidence-frame">
                <img src="/images/pin-documents-960.webp" alt={l.evidenceAlt} width={960} height={720} loading="lazy" />
                <MaskOverlay d={docs.d} width={docs.w} height={docs.h} point={docs.anchor ?? [0.5, 0.5]} />
                <span className="l-evidence-tag l-tag-point" style={{ left: `${(docs.anchor?.[0] ?? 0.5) * 100}%`, top: `${(docs.anchor?.[1] ?? 0.5) * 100}%` }}>
                  {l.tagPoint}
                </span>
                <span className="l-evidence-tag l-tag-mask">{l.tagMask}</span>
              </div>
              <figcaption className="l-quote-card">
                <Quote aria-hidden />
                <span>
                  <span className="l-quote" lang="en">
                    “in these white files in the bedroom cupboard”
                  </span>
                  <span className="l-quote-meta">
                    <CircleCheck aria-hidden /> {l.quoteMeta}
                  </span>
                </span>
              </figcaption>
            </figure>
            <div className="l-witness-copy">
              <h2 id="wit-title" className="l-h2">
                {l.witTitle}
              </h2>
              <ul className="l-witness-list">
                <li>
                  <Quote aria-hidden />
                  <span>
                    <strong>{d.witness.words}</strong>
                    {l.witWords}
                  </span>
                </li>
                <li>
                  <ScanEye aria-hidden />
                  <span>
                    <strong>{d.witness.pixels}</strong>
                    {l.witPixels}
                  </span>
                </li>
                <li>
                  <BookOpenCheck aria-hidden />
                  <span>
                    <strong>{d.witness.reading}</strong>
                    {l.witReading}
                  </span>
                </li>
              </ul>
              <p className="l-rule">{l.witRule}</p>
            </div>
          </div>
        </section>

        <section id="proof" className="l-section l-proof" aria-labelledby="proof-title">
          <div className="l-wrap">
            <div className="l-section-head">
              <h2 id="proof-title" className="l-h2">
                {l.proofTitle}
              </h2>
              <p className="l-lead">{l.proofBody}</p>
            </div>
            <div className="l-proof-grid">
              <figure className="l-shot l-shot-pass">
                <div className="l-shot-img">
                  <img src="/images/proof-right-720.webp" alt={l.proofRightAlt} width={720} height={proof.h} loading="lazy" />
                  <MaskOverlay d={proof.d} width={proof.w} height={proof.h} tone="ok" />
                </div>
                <figcaption>
                  <span className="chip chip-ok">
                    <CircleCheck aria-hidden />
                    {l.proofRight}
                  </span>
                  <span>{l.proofRightWhy}</span>
                </figcaption>
              </figure>
              <figure className="l-shot l-shot-fail">
                <div className="l-shot-img">
                  <img src="/images/proof-wrong-720.webp" alt={l.proofWrongAlt} width={720} height={525} loading="lazy" />
                </div>
                <figcaption>
                  <span className="chip chip-bad">
                    <CircleX aria-hidden />
                    {l.proofWrong}
                  </span>
                  <span>{l.proofWrongWhy}</span>
                </figcaption>
              </figure>
              <div className="l-tell">
                <p className="l-tell-head">
                  <Mic aria-hidden />
                  {l.tellHead}
                </p>
                <p className="l-tell-quote" lang="en">
                  “I run it at six every morning for twenty minutes until the tank is full. If it makes a grinding noise I switch it off straight away and call Sunil Mama.”
                </p>
                <ul className="l-tell-points">
                  {[l.tellPoint1, l.tellPoint2, l.tellPoint3].map((point) => (
                    <li key={point}>
                      <CircleCheck aria-hidden />
                      <span>{point}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        </section>

        <section id="board" className="l-section l-board" aria-labelledby="board-title">
          <div className="l-wrap l-split l-split-rev">
            <div className="l-board-copy">
              <h2 id="board-title" className="l-h2">
                {l.boardTitle}
              </h2>
              <p className="l-lead">{l.boardBody}</p>
              <Link to="/try" className="btn btn-primary">
                {l.boardCta}
              </Link>
            </div>
            <div className="l-board-mock" aria-label={l.boardMockLabel} role="img">
              <p className="l-mock-title">{format(d.board.titleLeaving, { name: 'Dilini' })}</p>
              <p className="l-mock-stat">{format(l.boardStop, { n: 4, total: 6 })}</p>
              <div className="job-strip" aria-hidden>
                {['covered', 'covered', 'at_risk', 'uncovered', 'uncovered', 'uncovered'].map((c, i) => (
                  <span key={i} className={`job-strip-seg seg-${c}`} />
                ))}
              </div>
              <ul className="l-mock-jobs">
                {PREVIEW.map((j) => (
                  <li key={j.en}>
                    <span>{lang === 'si' ? j.si : j.en}</span>
                    <span className={`chip ${j.c === 'covered' ? 'chip-ok' : j.c === 'at_risk' ? 'chip-risk' : 'chip-bad'}`}>{d.status[j.c]}</span>
                  </li>
                ))}
              </ul>
              <p className="l-mock-first">
                <Zap aria-hidden /> {l.boardFirst}
              </p>
            </div>
          </div>
        </section>

        <section className="l-section l-when" aria-labelledby="when-title">
          <div className="l-wrap">
            <h2 id="when-title" className="l-h2">
              {l.whenTitle}
            </h2>
            <div className="l-cards">
              <article className="l-card">
                <img src="/images/qr-phone-720.webp" alt="" width={720} height={640} loading="lazy" />
                <div className="l-card-body">
                  <h3>
                    <QrCode aria-hidden />
                    {l.whenQr}
                  </h3>
                  <p>{l.whenQrBody}</p>
                </div>
              </article>
              <article className="l-card">
                <img src="/images/power-cut-720.webp" alt="" width={720} height={720} loading="lazy" />
                <div className="l-card-body">
                  <h3>
                    <WifiOff aria-hidden />
                    {l.whenOffline}
                  </h3>
                  <p>{l.whenOfflineBody}</p>
                </div>
              </article>
              <article className="l-card l-card-wa">
                <div className="l-wa" aria-hidden>
                  <p className="l-wa-msg l-wa-me" lang="si">
                    කරන්ට් ගියා, මොකද කරන්නේ?
                  </p>
                  <p className="l-wa-msg l-wa-them" lang="si">
                    <strong>ප්‍රධාන ස්විච් පෙට්ටිය</strong>
                    <br />
                    1. කරන්ට් ගියොත් මුලින්ම මෙතනට එන්න.
                    <br />
                    2. පහළට වැටිලා තියෙන ස්විච් එක හොයාගෙන ඒක උඩට තල්ලු කරන්න.
                  </p>
                </div>
                <div className="l-card-body">
                  <h3>
                    <MessageCircle aria-hidden />
                    {l.whenWa}
                  </h3>
                  <p>{l.whenWaBody}</p>
                </div>
              </article>
            </div>
          </div>
        </section>

        <section className="l-section l-lang" aria-labelledby="lang-title">
          <div className="l-wrap l-split">
            <div>
              <h2 id="lang-title" className="l-h2">
                {l.langTitle}
              </h2>
              <p className="l-lead">{l.langBody}</p>
            </div>
            <div className="l-bilingual">
              <div className="l-bi-row">
                <span className="chip">
                  <Languages aria-hidden /> සිංහල
                </span>
                <p lang="si">කරන්ට් ගියොත් මුලින්ම මෙතනට එන්න.</p>
                <span className="l-bi-engine">Omnilingual ASR</span>
              </div>
              <div className="l-bi-row">
                <span className="chip">
                  <Languages aria-hidden /> English
                </span>
                <p lang="en">If the power goes off, come to this box first.</p>
                <span className="l-bi-engine">Muse Spark 1.3</span>
              </div>
            </div>
          </div>
        </section>

        <section id="privacy" className="l-section l-privacy" aria-labelledby="privacy-title">
          <div className="l-wrap l-split">
            <div>
              <h2 id="privacy-title" className="l-h2">
                {l.privTitle}
              </h2>
              <ul className="l-priv-list">
                <li>
                  <Lock aria-hidden />
                  {l.priv1}
                </li>
                <li>
                  <EyeOff aria-hidden />
                  {l.priv2}
                </li>
                <li>
                  <ShieldCheck aria-hidden />
                  {l.priv3}
                </li>
                <li>
                  <Sparkles aria-hidden />
                  {l.priv4}
                </li>
                <li>
                  <Trash2 aria-hidden />
                  {l.priv5}
                </li>
              </ul>
            </div>
            <div className="l-scrub" aria-label={l.scrubLabel} role="img">
              <p className="l-scrub-label">{l.scrubSaid}</p>
              <p className="l-scrub-in">
                The ATM PIN is <mark>4 8 2 1</mark>, it’s on the card.
              </p>
              <p className="l-scrub-label">{l.scrubSaved}</p>
              <p className="l-scrub-out">
                The ATM PIN is <span className="l-hidden-token">[hidden]</span>, it’s on the card.
              </p>
            </div>
          </div>
        </section>

        <section id="meta" className="l-section l-meta" aria-labelledby="meta-title">
          <div className="l-wrap">
            <h2 id="meta-title" className="l-h2">
              {l.metaTitle}
            </h2>
            <ul className="l-models">
              {[
                ['Muse Spark 1.3', 'muse-spark-1.3', l.metaSpark],
                ['SAM 3.1', 'sam-3.1', l.metaSam],
                ['Muse Voice Transcribe', 'muse-voice-transcribe-1.0', l.metaVoice],
                ['Muse Wonder', 'muse-wonder-1.0', l.metaWonder],
                ['Omnilingual ASR', 'omniASR_LLM_1B_v2', l.metaOmni],
                ['Muse Image', 'muse-image-1.0', l.metaImage],
                ['Muse Spark Open', 'muse-spark-open', l.metaOpen],
              ].map(([name, id, body]) => (
                <li key={name} className="l-model">
                  <h3>{name}</h3>
                  <code>{id}</code>
                  <p>{body}</p>
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section className="l-section l-for" aria-labelledby="for-title">
          <div className="l-wrap">
            <div className="l-section-head">
              <h2 id="for-title" className="l-h2">
                {l.forTitle}
              </h2>
              <p className="help-text">{l.forNote}</p>
            </div>
            <div className="l-cards">
              {(
                [
                  ['abroad', l.for1, l.for1Body, 600],
                  ['sea', l.for2, l.for2Body, 698],
                  ['home', l.for3, l.for3Body, 720],
                ] as const
              ).map(([img, title, body, h]) => (
                <article key={img} className="l-card l-card-photo">
                  <img src={`/images/${img}-960.webp`} alt="" width={960} height={h} loading="lazy" />
                  <div className="l-card-body">
                    <h3>{title}</h3>
                    <p>{body}</p>
                  </div>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className="l-final" aria-labelledby="final-title">
          <div className="l-final-card">
            <h2 id="final-title">{l.finalTitle}</h2>
            <p>{l.finalBody}</p>
            <div className="l-final-ctas">
              <Link to="/try" className="btn btn-primary">
                {l.heroCta}
              </Link>
              {live && (
                <Link to="/start" className="btn btn-ghost-dark">
                  {l.startOwn}
                </Link>
              )}
            </div>
          </div>
        </section>
      </main>

      <footer className="l-footer">
        <div className="l-wrap l-footer-grid">
          <div>
            <Logo size={30} />
            <p>{l.footerBy}</p>
            <p className="help-text">{l.footerLicense}</p>
          </div>
          <nav aria-label={l.footerNav} className="l-footer-links">
            <Link to="/rules">{l.footerPolicy}</Link>
            <Link to="/credits">{l.footerCredits}</Link>
            {SOURCE_URL && (
              <a href={SOURCE_URL} rel="noopener noreferrer">
                {l.footerCode}
              </a>
            )}
            <a href="/api/docs">{l.footerApi}</a>
          </nav>
        </div>
      </footer>
    </div>
  );
}
