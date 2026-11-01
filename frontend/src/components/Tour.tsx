/* The guided tour: a first-visit welcome, then one popover per step that moves through the sample
   home's pages and spotlights the part being explained, from the walk-through to the evidence.

   It runs only on the landing page and on a copy of the sample home, never on a real home, and
   everything it says is about the sample home's real recorded runs. The dimmed area is drawn but
   lets clicks through, so the visitor can try each thing while the step explains it. Progress is
   kept in this browser only (localStorage), so a reload carries on from the same step.

   English only, by design: the app itself stays bilingual. */
import { ArrowLeft, ArrowRight, Compass, MousePointerClick, X } from 'lucide-react';
import { useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { getToken, lastHousehold } from '../lib/api';
import { navigate, useLocation } from '../lib/router';
import { LogoMark } from './Logo';

export const TOUR_EVENT = 'iid:tour';
const KEY = 'iid.tour.v1';
const SANDBOX = 'demo-';

type Status = 'new' | 'active' | 'done' | 'skipped';
type State = { status: Status; step: number; hid?: string };

type Step = {
  id: string;
  /** Page inside the household, '' for the board. */
  route: string;
  /** Tried in order; the first that is on the page is spotlit. */
  targets: string[];
  /** Clicked when the step opens, if it is there and not already chosen (a tab, say). */
  enter?: string;
  title: string;
  body: ReactNode;
  tryIt?: ReactNode;
  models?: string[];
};

const STEPS: Step[] = [
  {
    id: 'board',
    route: '',
    targets: ['.board-hero'],
    title: 'If she left tomorrow, what would stop?',
    body: 'Dilini leaves for two years. The board answers her family’s real question: code simulates every day of her time away and counts the jobs nobody at home can do yet.',
  },
  {
    id: 'timeline',
    route: '',
    targets: ['.timeline'],
    title: 'Her time away, month by month',
    body: 'Each bar is a month. Its red top is a job that comes due with nobody proven to do it. A proof lasts 120 days, so a job that is fine today can stop in month five.',
  },
  {
    id: 'jobs',
    route: '',
    targets: ['.job-list'],
    title: 'Six jobs, and who can do each',
    body: 'Every job shows who has proven they can do it: someone can, still learning, or nobody yet. “Not enough was recorded” is kept apart from “nobody can do it”.',
    tryIt: 'Open any job to see her clip and her steps.',
  },
  {
    id: 'record',
    route: 'record',
    targets: ['.pipeline'],
    title: 'One walk through the house',
    body: 'Dilini filmed the house once and talked, in Sinhala and English. Six steps turn that video into checked facts: each one is done by a Meta model and checked by code.',
    models: ['Omnilingual ASR (Sinhala)', 'Muse Voice Transcribe', 'SAM 3.1', 'Muse Spark 1.3', 'Muse Wonder 1.0'],
  },
  {
    id: 'review',
    route: 'review',
    targets: ['.claims .claim', '.claims'],
    title: 'Every fact, with its witnesses',
    body: (
      <>
        Each fact carries her exact words, and three witnesses check it. <b>The words:</b> code finds the quote word for word. <b>The picture:</b> Muse Spark’s point must land inside SAM 3.1’s outline. <b>Second reading:</b> Muse Wonder re-reads anything about electricity, gas or fire. If they disagree, the fact waits for her.
      </>
    ),
    tryIt: 'Accept or reject a fact. Nothing reaches the family until she does.',
    models: ['Muse Spark 1.3', 'SAM 3.1', 'Muse Wonder 1.0'],
  },
  {
    id: 'unused',
    route: 'review',
    enter: '.tabs [role="tab"]:nth-child(2)',
    targets: ['.left-out', '.claims', '.tabs'],
    title: 'What is never kept',
    body: 'Before anything is stored, SAM 3.1 finds bank cards and code blurs them. Spoken codes are hidden and silenced. Medicine is never turned into a step: code refuses it and says why.',
    models: ['SAM 3.1'],
  },
  {
    id: 'task',
    route: 'task/main_switch',
    targets: ['.task-clip', '.task-head'],
    title: 'Her own clip, with the object followed',
    body: 'SAM 3.1 follows the switch box through her video, frame by frame. Each step keeps her own Sinhala words and the second she said them.',
    tryIt: 'Play the clip, or tap a step to jump to the moment she said it.',
    models: ['SAM 3.1'],
  },
  {
    id: 'show',
    route: 'prove?person=p-nethum&task=water_pump',
    targets: ['section.proof-card[aria-labelledby="show-title"]', '.proof-area', '.pick'],
    title: 'Prove it: show me',
    body: 'Before she leaves, each person proves each job. Nethum photographs the pump: SAM 3.1 must find a pump in his photo, and Muse Spark must match it to her still. If it can’t tell, the answer is no.',
    tryIt: 'Tap “A different one”, then “The right one”.',
    models: ['SAM 3.1', 'Muse Spark 1.3'],
  },
  {
    id: 'tell',
    route: 'prove?person=p-nethum&task=water_pump',
    targets: ['section.proof-card[aria-labelledby="tell-title"]', '.proof-area'],
    title: 'Prove it: tell me',
    body: 'Then he explains the job in his own words, spoken or typed. Every point must be covered, the safety step included, and steps pasted back are refused.',
    tryIt: 'Try the sample answer that leaves out the safety step.',
    models: ['Muse Voice Transcribe', 'Muse Spark 1.3'],
  },
  {
    id: 'help',
    route: 'help',
    targets: ['.suggest', '.ask'],
    title: 'While she’s away, they just ask',
    body: 'The help line answers only with what she recorded. Muse Spark picks the job inside a fence and can’t give advice of its own. Gas, fire or a shock: code shows the emergency numbers first.',
    tryIt: 'Tap “I can smell gas in the kitchen”.',
    models: ['Muse Spark 1.3'],
  },
  {
    id: 'whatsapp',
    route: 'help',
    targets: ['.wa'],
    title: 'The same help, on WhatsApp',
    body: 'For family who won’t install an app, the help line works on WhatsApp too, in Sinhala or English. This preview shows exactly what it would reply.',
    tryIt: 'Ask it something in Sinhala, like “කරන්ට් ගියා”.',
    models: ['Muse Spark 1.3'],
  },
  {
    id: 'stickers',
    route: 'card?tab=stickers',
    targets: ['.stickers', '.app-main .tabs'],
    title: 'A sticker on every object',
    body: 'Print the fridge card and a QR sticker for each job. A sticker opens only its own job, her clip and her steps, with no login and nothing else from the house.',
  },
  {
    id: 'offline',
    route: 'card?tab=offline',
    targets: ['.offline', '.app-main .tabs'],
    title: 'No power, no internet, still works',
    body: 'Save the home on the phone. When the power is off and the Wi-Fi is down, the board and every sticker still open.',
  },
  {
    id: 'evidence',
    route: 'evidence',
    targets: ['.chain'],
    title: 'How we know',
    body: 'Every model answer, check and decision is in a hash-chained log, so nothing can change quietly. Models read; code decides.',
  },
];

const LAST = STEPS.length; // the finish card comes after the last step

function load(): State {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) {
      const s = JSON.parse(raw) as State;
      if (s && typeof s.step === 'number' && ['new', 'active', 'done', 'skipped'].includes(s.status)) return s;
    }
  } catch {
    /* storage may be blocked: the tour still runs for this visit */
  }
  return { status: 'new', step: 0 };
}

function save(s: State) {
  try {
    localStorage.setItem(KEY, JSON.stringify(s));
  } catch {
    /* ignore */
  }
}

/** Start the tour from anywhere (the button in a sample home's top bar). */
export function startTour() {
  window.dispatchEvent(new CustomEvent(TOUR_EVENT, { detail: 'start' }));
}

function sandboxOf(path: string): string | null {
  const m = /^\/h\/([^/]+)/.exec(path);
  return m && m[1].startsWith(SANDBOX) ? m[1] : null;
}

function stepPath(hid: string, step: Step) {
  return `/h/${hid}${step.route ? `/${step.route}` : ''}`;
}

function onStepPage(step: Step, hid: string): boolean {
  const want = new URL(stepPath(hid, step), location.origin);
  if (location.pathname !== want.pathname) return false;
  const have = new URLSearchParams(location.search);
  for (const [k, v] of want.searchParams) if (have.get(k) !== v) return false;
  return true;
}

const reduced = () => typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches;

export function Tour() {
  const { path } = useLocation();
  const [state, setState] = useState<State>(load);
  const update = useCallback((s: State) => {
    setState(s);
    save(s);
  }, []);

  const here = sandboxOf(path);
  const onLanding = path === '/';
  const hid = here || state.hid || null;

  // Start or restart, from the welcome card, the finish card or the top bar's button.
  const begin = useCallback(
    (from: string | null) => {
      const target = from && getToken(from) ? from : lastHousehold();
      if (target && target.startsWith(SANDBOX) && getToken(target)) {
        update({ status: 'active', step: 0, hid: target });
        navigate(stepPath(target, STEPS[0]));
      } else {
        update({ status: 'active', step: 0 });
        navigate('/try');
      }
    },
    [update],
  );

  useEffect(() => {
    const on = (e: Event) => {
      if ((e as CustomEvent).detail === 'start') begin(sandboxOf(location.pathname));
    };
    window.addEventListener(TOUR_EVENT, on);
    return () => window.removeEventListener(TOUR_EVENT, on);
  }, [begin]);

  // A new copy of the sample (the /try page made one): the tour follows it.
  useEffect(() => {
    if (state.status === 'active' && here && state.hid !== here) update({ ...state, hid: here });
  }, [here, state, update]);

  const close = useCallback(() => update({ ...state, status: 'done' }), [state, update]);
  const skip = useCallback(() => update({ ...state, status: 'skipped' }), [state, update]);

  if (state.status === 'new' && (onLanding || here)) {
    return <Welcome onStart={() => begin(here)} onSkip={skip} />;
  }
  if (state.status === 'active' && here && hid) {
    if (state.step >= LAST) return <Finish onRestart={() => begin(hid)} onClose={close} />;
    return <Popover key={`${state.step}`} hid={hid} index={state.step} onGo={(i) => update({ ...state, step: i, hid })} onClose={close} />;
  }
  if (onLanding && state.status === 'active' && state.hid && getToken(state.hid)) {
    const resumeAt = state.hid;
    return (
      <button type="button" className="tour-launch" onClick={() => navigate(stepPath(resumeAt, STEPS[Math.min(state.step, LAST - 1)]))}>
        <Compass aria-hidden />
        Carry on with the tour
      </button>
    );
  }
  if (onLanding && state.status !== 'new') {
    return (
      <button type="button" className="tour-launch" onClick={() => begin(null)}>
        <Compass aria-hidden />
        Take the guided tour
      </button>
    );
  }
  return null;
}

// ------------------------------------------------------------------ the welcome and finish cards
function useDialogFocus(ref: React.RefObject<HTMLElement | null>, onEscape: () => void) {
  const esc = useRef(onEscape);
  esc.current = onEscape;
  useEffect(() => {
    const before = document.activeElement as HTMLElement | null;
    ref.current?.querySelector<HTMLElement>('[data-autofocus]')?.focus({ preventScroll: true });
    ref.current?.scrollTo?.({ top: 0 });
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') esc.current();
      if (e.key !== 'Tab' || !ref.current) return;
      const items = [...ref.current.querySelectorAll<HTMLElement>('button, a[href]')].filter((n) => !n.hasAttribute('disabled'));
      if (!items.length) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('keydown', onKey);
      before?.focus?.();
    };
  }, [ref]);
}

function Welcome({ onStart, onSkip }: { onStart: () => void; onSkip: () => void }) {
  const box = useRef<HTMLDivElement>(null);
  useDialogFocus(box, onSkip);
  return (
    <div className="tour-backdrop">
      <div className="tour-modal" role="dialog" aria-modal="true" aria-labelledby="tour-welcome-title" aria-describedby="tour-welcome-body" ref={box}>
        <div className="tour-modal-mark">
          <LogoMark size={44} />
        </div>
        <p className="tour-kicker">A guided tour, about three minutes</p>
        <h2 id="tour-welcome-title">See the whole handover, step by step</h2>
        <p id="tour-welcome-body" className="tour-lead">
          When a parent leaves Sri Lanka to work abroad, the house still has to run. This tour walks you through If I Disappear on a sample home: Dilini is leaving for two years, and her family stays.
        </p>
        <ol className="tour-journey">
          <li>
            <b>Walk.</b> She films the house once and explains it.
          </li>
          <li>
            <b>Check.</b> Meta’s models read it, and code checks every fact.
          </li>
          <li>
            <b>Prove.</b> Each person shows and tells each job before she goes.
          </li>
          <li>
            <b>Away.</b> A help line, stickers, and a copy that works offline.
          </li>
        </ol>
        <p className="tour-note">Every model answer in the sample is a real recorded run of Meta’s models, and every check runs live as you click. Your copy is yours alone, so change anything.</p>
        <div className="tour-modal-actions">
          <button type="button" className="btn btn-primary" onClick={onStart} data-autofocus>
            Start the tour
          </button>
          <button type="button" className="btn btn-quiet tour-quiet" onClick={onSkip}>
            Explore on my own
          </button>
        </div>
      </div>
    </div>
  );
}

function Finish({ onRestart, onClose }: { onRestart: () => void; onClose: () => void }) {
  const box = useRef<HTMLDivElement>(null);
  useDialogFocus(box, onClose);
  return (
    <div className="tour-backdrop">
      <div className="tour-modal" role="dialog" aria-modal="true" aria-labelledby="tour-finish-title" ref={box}>
        <div className="tour-modal-mark">
          <LogoMark size={44} />
        </div>
        <p className="tour-kicker">That’s the whole journey</p>
        <h2 id="tour-finish-title">When she’s away, what she knows stays home</h2>
        <p className="tour-lead">She walked the house once, her family proved each job, and they get help while she’s away. Everything you saw ran on Meta’s models, with code deciding what to trust.</p>
        <ul className="tour-facts">
          <li>Restart the tour any time with the compass button at the top.</li>
          <li>The sample home is yours to change: accept facts, prove jobs, ask the help line.</li>
          <li>With an invite code, you can record a home of your own at /start.</li>
        </ul>
        <div className="tour-modal-actions">
          <button type="button" className="btn btn-primary" onClick={onClose} data-autofocus>
            Explore on my own
          </button>
          <button type="button" className="btn btn-quiet tour-quiet" onClick={onRestart}>
            Start the tour again
          </button>
        </div>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ one step: spotlight + popover
type Box = { top: number; left: number; width: number; height: number };

function Popover({ hid, index, onGo, onClose }: { hid: string; index: number; onGo: (i: number) => void; onClose: () => void }) {
  const step = STEPS[index];
  const card = useRef<HTMLDivElement>(null);
  const spot = useRef<HTMLDivElement>(null);
  const title = useRef<HTMLHeadingElement>(null);
  const [target, setTarget] = useState<HTMLElement | null>(null);
  const [missing, setMissing] = useState(false);

  // Go to the step's page, then wait for its part of the page to appear.
  useEffect(() => {
    if (!onStepPage(step, hid)) navigate(stepPath(hid, step));
    let done = false;
    const t0 = Date.now();
    let entered = false;
    const find = () => {
      if (done) return;
      if (step.enter && !entered) {
        const tab = document.querySelector<HTMLElement>(step.enter);
        if (tab) {
          entered = true;
          if (tab.getAttribute('aria-selected') !== 'true') tab.click();
        }
      }
      // The first selector is the real target; the others stand in only if it never shows.
      for (const [i, sel] of step.targets.entries()) {
        if (i > 0 && Date.now() - t0 < 2500) break;
        const el = document.querySelector<HTMLElement>(sel);
        if (el && el.getBoundingClientRect().height > 0 && (!step.enter || entered || Date.now() - t0 > 1500)) {
          done = true;
          reveal(el);
          setTarget(el);
          return;
        }
      }
      if (Date.now() - t0 > 6000) {
        done = true;
        setMissing(true);
        return;
      }
      window.setTimeout(find, 120);
    };
    find();
    return () => {
      done = true;
    };
  }, [step, hid]);

  // Keep the spotlight and the card on the target as the page scrolls, resizes or loads images.
  useLayoutEffect(() => {
    let raf = 0;
    let last = '';
    const place = () => {
      raf = requestAnimationFrame(place);
      const c = card.current;
      const s = spot.current;
      if (!c) return;
      const vw = window.innerWidth;
      const vh = window.innerHeight;
      const mobile = vw < 760;
      let r: Box | null = null;
      if (target && !target.isConnected) {
        for (const sel of step.targets) {
          const el = document.querySelector<HTMLElement>(sel);
          if (el && el.getBoundingClientRect().height > 0) {
            setTarget(el);
            break;
          }
        }
      }
      if (target && target.isConnected) {
        const b = target.getBoundingClientRect();
        const top = Math.max(b.top - 8, mobile ? topBarBottom() + 4 : 8);
        const bottom = Math.min(b.bottom + 8, vh - 8);
        if (bottom > top + 12) r = { top, left: Math.max(b.left - 8, 6), width: Math.min(b.width + 16, vw - 12), height: bottom - top };
      }
      const key = r ? `${Math.round(r.top)},${Math.round(r.left)},${Math.round(r.width)},${Math.round(r.height)},${vw},${vh}` : `none,${vw},${vh}`;
      if (key === last) return;
      last = key;
      if (s) {
        s.style.opacity = r ? '1' : '0';
        if (r) Object.assign(s.style, { top: `${r.top}px`, left: `${r.left}px`, width: `${r.width}px`, height: `${r.height}px` });
      }
      if (mobile) {
        c.dataset.place = 'sheet';
        Object.assign(c.style, { top: '', left: '', right: '', bottom: '', width: '' });
        return;
      }
      const right = r ? vw - (r.left + r.width) - 18 - 16 : 0;
      const left = r ? r.left - 18 - 16 : 0;
      const side = r && right >= 300 ? 'right' : r && left >= 300 ? 'left' : '';
      c.style.width = side ? `${Math.min(400, side === 'right' ? right : left)}px` : '';
      const w = c.offsetWidth;
      const h = c.offsetHeight;
      let x: number;
      let y: number;
      let where = 'center';
      if (!r) {
        x = (vw - w) / 2;
        y = (vh - h) / 2;
      } else if (side === 'right') {
        x = r.left + r.width + 18;
        y = clamp(r.top, 16, vh - h - 16);
        where = 'right';
      } else if (side === 'left') {
        x = r.left - 18 - w;
        y = clamp(r.top, 16, vh - h - 16);
        where = 'left';
      } else if (r.top + r.height + 18 + h <= vh - 16) {
        x = clamp(r.left + r.width / 2 - w / 2, 16, vw - w - 16);
        y = r.top + r.height + 18;
        where = 'below';
      } else if (r.top - 18 - h >= 16) {
        x = clamp(r.left + r.width / 2 - w / 2, 16, vw - w - 16);
        y = r.top - 18 - h;
        where = 'above';
      } else {
        x = vw - w - 16;
        y = vh - h - 16;
        where = 'corner';
      }
      c.dataset.place = where;
      Object.assign(c.style, { left: `${x}px`, top: `${y}px`, right: '', bottom: '' });
    };
    raf = requestAnimationFrame(place);
    return () => cancelAnimationFrame(raf);
  }, [target, missing, step]);

  // Each new step is announced: focus moves to its title.
  useEffect(() => {
    title.current?.focus({ preventScroll: true });
  }, [index]);

  const next = useCallback(() => onGo(index + 1), [index, onGo]);
  const back = useCallback(() => index > 0 && onGo(index - 1), [index, onGo]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing = e.target instanceof HTMLElement && /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName);
      if (e.key === 'Escape') onClose();
      else if (!typing && e.key === 'ArrowRight') next();
      else if (!typing && e.key === 'ArrowLeft') back();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [next, back, onClose]);

  const n = index + 1;
  return (
    <>
      <div className="tour-spot" ref={spot} aria-hidden />
      <div className={`tour-card${missing ? ' tour-card-missing' : ''}`} ref={card} role="dialog" aria-modal="false" aria-labelledby="tour-step-title" aria-describedby="tour-step-body">
        <div className="tour-card-head">
          <span className="tour-count">
            Step {n} of {STEPS.length}
          </span>
          <button type="button" className="tour-x" onClick={onClose} aria-label="End the tour">
            <X aria-hidden />
          </button>
        </div>
        <div className="tour-progress" aria-hidden>
          <span style={{ width: `${(n / STEPS.length) * 100}%` }} />
        </div>
        <h2 id="tour-step-title" ref={title} tabIndex={-1}>
          {step.title}
        </h2>
        <p id="tour-step-body" className="tour-body">
          {step.body}
        </p>
        {step.tryIt && (
          <p className="tour-try">
            <MousePointerClick aria-hidden />
            <span>{step.tryIt}</span>
          </p>
        )}
        {step.models && (
          <div className="tour-models">
            <span className="tour-models-label">Meta models at work</span>
            <ul>
              {step.models.map((m) => (
                <li key={m}>{m}</li>
              ))}
            </ul>
          </div>
        )}
        <div className="tour-actions">
          {index > 0 ? (
            <button type="button" className="tour-back" onClick={back}>
              <ArrowLeft aria-hidden />
              Back
            </button>
          ) : (
            <span />
          )}
          <button type="button" className="btn btn-primary tour-next" onClick={next}>
            {n === STEPS.length ? 'Finish' : 'Next'}
            <ArrowRight aria-hidden />
          </button>
        </div>
      </div>
    </>
  );
}

function clamp(v: number, a: number, b: number) {
  return Math.min(Math.max(v, a), Math.max(a, b));
}

function topBarBottom(): number {
  const bar = document.querySelector('.topbar');
  return bar ? bar.getBoundingClientRect().bottom : 0;
}

/** Scroll the target into view: centred on a wide screen; on a phone, just under the top bar, so
 * the card at the bottom doesn't cover it. */
function reveal(el: HTMLElement) {
  const behavior: ScrollBehavior = reduced() ? 'auto' : 'smooth';
  const b = el.getBoundingClientRect();
  if (window.innerWidth < 760) {
    const y = window.scrollY + b.top - topBarBottom() - 12;
    window.scrollTo({ top: Math.max(0, y), behavior });
  } else {
    const room = window.innerHeight;
    const y = b.height < room - 120 ? window.scrollY + b.top - (room - b.height) / 2 : window.scrollY + b.top - 90;
    window.scrollTo({ top: Math.max(0, y), behavior });
  }
}
