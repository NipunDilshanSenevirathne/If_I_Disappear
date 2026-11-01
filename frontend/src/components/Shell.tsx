import { ArrowLeft, BadgeCheck, Compass, EllipsisVertical, FileCheck2, History, House, LifeBuoy, LogOut, Monitor, Moon, QrCode, Sun, Users, Video, X } from 'lucide-react';
import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { format, useI18n, type Lang } from '../i18n';
import { Link, navigate } from '../lib/router';
import type { Board } from '../lib/types';
import { modelName } from '../lib/witness';
import { LogoMark } from './Logo';
import { startTour } from './Tour';

export type HouseholdCtx = {
  id: string;
  board: Board;
  refresh: () => Promise<void>;
  minutes: number;
  setMinutes: (n: number) => void;
};

export const HouseholdContext = createContext<HouseholdCtx | null>(null);

export function useHousehold(): HouseholdCtx {
  const ctx = useContext(HouseholdContext);
  if (!ctx) throw new Error('No household');
  return ctx;
}

export function LangToggle({ dark = false }: { dark?: boolean }) {
  const { lang, setLang, d } = useI18n();
  const options: { value: Lang; label: string; short: string }[] = [
    { value: 'en', label: 'English', short: 'EN' },
    { value: 'si', label: 'සිංහල', short: 'සිං' },
  ];
  return (
    <div className={`lang-toggle${dark ? ' lang-toggle-dark' : ''}`} role="group" aria-label={d.lang.label}>
      {options.map((o) => (
        <button key={o.value} type="button" lang={o.value} aria-pressed={lang === o.value} aria-label={o.label} onClick={() => setLang(o.value)}>
          {o.short}
        </button>
      ))}
    </div>
  );
}

type Theme = 'auto' | 'light' | 'dark';
function readTheme(): Theme {
  try {
    const v = localStorage.getItem('iid.theme');
    return v === 'light' || v === 'dark' ? v : 'auto';
  } catch {
    return 'auto';
  }
}
export function applyTheme(theme: Theme = readTheme()) {
  if (theme === 'auto') document.documentElement.removeAttribute('data-theme');
  else document.documentElement.setAttribute('data-theme', theme);
}

function ThemeSwitch() {
  const { d } = useI18n();
  const [theme, setTheme] = useState<Theme>(readTheme);
  const choose = (t: Theme) => {
    setTheme(t);
    try {
      localStorage.setItem('iid.theme', t);
    } catch {
      /* ignore */
    }
    applyTheme(t);
  };
  const items: { value: Theme; icon: typeof Sun; label: string }[] = [
    { value: 'light', icon: Sun, label: d.menu.light },
    { value: 'dark', icon: Moon, label: d.menu.dark },
    { value: 'auto', icon: Monitor, label: d.menu.auto },
  ];
  return (
    <div className="theme-switch" role="group" aria-label={d.menu.theme}>
      {items.map(({ value, icon: Icon, label }) => (
        <button key={value} type="button" aria-pressed={theme === value} onClick={() => choose(value)}>
          <Icon aria-hidden />
          <span>{label}</span>
        </button>
      ))}
    </div>
  );
}

function Menu({ id, owner }: { id: string; owner: boolean }) {
  const { d } = useI18n();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => !box.current?.contains(e.target as Node) && setOpen(false);
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false);
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDoc);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);
  const go = (to: string) => {
    setOpen(false);
    navigate(to);
  };
  return (
    <div className="menu" ref={box}>
      <button type="button" className="icon-btn" aria-haspopup="true" aria-expanded={open} aria-label={d.menu.open} onClick={() => setOpen((v) => !v)}>
        {open ? <X aria-hidden /> : <EllipsisVertical aria-hidden />}
      </button>
      {open && (
        <div className="menu-panel">
          <nav aria-label={d.menu.open}>
            {owner && (
              <button type="button" onClick={() => go(`/h/${id}/review`)}>
                <FileCheck2 aria-hidden />
                {d.nav.review}
              </button>
            )}
            <button type="button" onClick={() => go(`/h/${id}/people`)}>
              <Users aria-hidden />
              {owner ? d.people.title : d.menu.settings}
            </button>
            {owner && (
              <button type="button" onClick={() => go(`/h/${id}/evidence`)}>
                <History aria-hidden />
                {d.nav.evidence}
              </button>
            )}
            <button type="button" onClick={() => go('/')}>
              <LogOut aria-hidden />
              {d.menu.leave}
            </button>
          </nav>
          <ThemeSwitch />
        </div>
      )}
    </div>
  );
}

export function TopBar({ title, back }: { title?: string; back?: string }) {
  const { id, board } = useHousehold();
  const { d } = useI18n();
  const owner = board.you.role === 'owner';
  return (
    <header className="topbar">
      <div className="topbar-inner">
        {back ? (
          <Link to={back} className="icon-btn topbar-back" aria-label={d.common.back}>
            <ArrowLeft aria-hidden />
          </Link>
        ) : (
          <Link to={`/h/${id}`} className="topbar-home" aria-label={d.nav.home}>
            <LogoMark size={34} />
          </Link>
        )}
        <div className="topbar-title">
          <span className="topbar-name">{title || board.household.name}</span>
          {board.sample && <span className="chip chip-lamp topbar-chip">{d.common.sample}</span>}
        </div>
        {board.sample && (
          <button type="button" className="icon-btn topbar-tour" onClick={startTour} aria-label="Guided tour" title="Guided tour">
            <Compass aria-hidden />
          </button>
        )}
        <LangToggle dark />
        <Menu id={id} owner={owner} />
      </div>
    </header>
  );
}

export function BottomNav({ current }: { current: string }) {
  const { id, board } = useHousehold();
  const { d } = useI18n();
  const owner = board.you.role === 'owner';
  const items = [
    { key: 'home', to: `/h/${id}`, icon: House, label: d.nav.home },
    ...(owner ? [{ key: 'record', to: `/h/${id}/record`, icon: Video, label: d.nav.record }] : []),
    { key: 'prove', to: `/h/${id}/prove`, icon: BadgeCheck, label: d.nav.prove },
    { key: 'help', to: `/h/${id}/help`, icon: LifeBuoy, label: d.nav.help },
    { key: 'card', to: `/h/${id}/card`, icon: QrCode, label: d.nav.card },
  ];
  return (
    <nav className="bottomnav" aria-label={d.nav.main}>
      {items.map(({ key, to, icon: Icon, label }) => (
        <Link key={key} to={to} className="bottomnav-item" aria-current={current === key ? 'page' : undefined}>
          <Icon aria-hidden />
          <span>{label}</span>
        </Link>
      ))}
    </nav>
  );
}

export function SampleBanner() {
  const { board } = useHousehold();
  const { d } = useI18n();
  const [open, setOpen] = useState(false);
  if (!board.sample) return null;
  // Says which models the sample's recorded runs really came from (written by the sample builder).
  const sources = board.sample_sources ?? { reading: 'muse-spark-open', outlines: 'sample' };
  const name = modelName(sources.reading);
  const long = /open/i.test(sources.reading) ? format(d.common.openModel, { model: name }) : name;
  const note = sources.outlines === 'sample' ? d.common.sampleNote : d.common.sampleNoteSam;
  return (
    <aside className="sample-banner">
      <button type="button" className="sample-banner-head" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        <span className="chip chip-lamp">{d.common.sample}</span>
        <span>{format(d.common.sampleShort, { model: name })}</span>
      </button>
      {open && <p className="sample-banner-body">{format(note, { model: long })}</p>}
    </aside>
  );
}

export function PageTitle({ title, sub, children }: { title: ReactNode; sub?: ReactNode; children?: ReactNode }) {
  return (
    <div className="page-title">
      <h1>{title}</h1>
      {sub && <p className="page-sub">{sub}</p>}
      {children}
    </div>
  );
}
