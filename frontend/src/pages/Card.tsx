import { Check, Copy, Download, Printer, RefreshCw, Share2, Zap, Flame, Droplets } from 'lucide-react';
import { useState } from 'react';
import { EmergencyNumbers, ErrorState, Loading, messageOf, useToast } from '../components/Common';
import { LogoMark } from '../components/Logo';
import { QR } from '../components/QR';
import { PageTitle, SampleBanner, useHousehold } from '../components/Shell';
import { format, useI18n } from '../i18n';
import { Api, setToken } from '../lib/api';
import { dateTime } from '../lib/format';
import { useAsync } from '../lib/hooks';
import { forgetOffline, offlineSupported, saveOffline, savedOffline } from '../lib/offline';
import { navigate, useLocation } from '../lib/router';

type Tab = 'card' | 'stickers' | 'links' | 'offline';
const SAFETY_ICON = { electricity: Zap, gas: Flame, fire: Flame, water: Droplets } as Record<string, typeof Zap>;

function here(url: string): string {
  try {
    const u = new URL(url, location.origin);
    return `${location.origin}${u.pathname}${u.search}`;
  } catch {
    return url;
  }
}

function useLinks(id: string, owner: boolean) {
  return useAsync(() => (owner ? Api.links(id) : Promise.resolve(null)), [id, owner]);
}

function FridgeCard({ stickers }: { stickers: Record<string, string> }) {
  const { board } = useHousehold();
  const { d } = useI18n();
  return (
    <article className="fridge print-area" aria-label={d.card.cardTab}>
      <header className="fridge-head">
        <LogoMark size={44} />
        <div>
          <h2>{board.household.name}</h2>
          {board.leaving?.name && <p>{format(d.card.cardBy, { name: board.leaving.name })}</p>}
        </div>
      </header>
      <div className="fridge-sos">
        <p>
          <strong>{d.card.sos}</strong> <span lang="si">හදිසි අවස්ථාවකදී</span>
        </p>
        <EmergencyNumbers compact />
      </div>
      <ol className="fridge-jobs">
        {board.tasks.map((t) => {
          const Icon = SAFETY_ICON[t.safety];
          return (
            <li key={t.key} className="fridge-job">
              <div className="fridge-job-text">
                <h3>
                  {Icon && <Icon aria-hidden />}
                  <span lang="si">{t.title_si || t.title_en}</span>
                  <span className="fridge-en">{t.title_en}</span>
                </h3>
                <ol>
                  {t.steps.slice(0, 3).map((s) => (
                    <li key={s.id}>
                      <span lang="si">{s.text_si || s.text_en}</span>
                      <span className="fridge-en">{s.text_en}</span>
                    </li>
                  ))}
                </ol>
                {t.warnings.slice(0, 1).map((w) => (
                  <p key={w.id} className="fridge-warn">
                    <span lang="si">{w.text_si || w.text_en}</span> <span className="fridge-en">{w.text_en}</span>
                  </p>
                ))}
              </div>
              {stickers[t.key] && <QR value={here(stickers[t.key])} size={92} label={`${d.card.scan}: ${t.title_en}`} />}
            </li>
          );
        })}
      </ol>
      <footer className="fridge-foot">
        <span>{d.card.scan}</span> <span lang="si">කොහොමද කියලා බලන්න ස්කෑන් කරන්න</span>
      </footer>
    </article>
  );
}

function Stickers({ links, only }: { links: NonNullable<Awaited<ReturnType<typeof Api.links>>>; only?: string | null }) {
  const { d } = useI18n();
  const list = only ? links.stickers.filter((s) => s.task_key === only) : links.stickers;
  return (
    <div className="stickers print-area">
      {list.map((s) => {
        const Icon = SAFETY_ICON[s.safety];
        return (
          <article key={s.task_key} className={`sticker sticker-${s.safety}`}>
            <QR value={here(s.url)} size={150} label={`${d.card.scan}: ${s.title_en}`} />
            <div className="sticker-text">
              <p className="sticker-title" lang="si">
                {Icon && <Icon aria-hidden />}
                {s.title_si || s.title_en}
              </p>
              <p className="sticker-en">{s.title_en}</p>
              <p className="sticker-scan">
                <span lang="si">ස්කෑන් කරන්න</span>
                <span>Scan me</span>
              </p>
            </div>
            <LogoMark size={26} />
          </article>
        );
      })}
    </div>
  );
}

function PeopleLinks({ links, onRotated }: { links: NonNullable<Awaited<ReturnType<typeof Api.links>>>; onRotated: () => void }) {
  const { id } = useHousehold();
  const { d } = useI18n();
  const toast = useToast();
  const [copied, setCopied] = useState<string | null>(null);
  const [confirm, setConfirm] = useState(false);
  const copy = async (pid: string, url: string) => {
    try {
      await navigator.clipboard.writeText(here(url));
      setCopied(pid);
      window.setTimeout(() => setCopied(null), 2000);
    } catch {
      toast(here(url));
    }
  };
  const share = async (name: string, url: string) => {
    try {
      await navigator.share({ title: 'If I Disappear', text: format(d.card.shareText, { name }), url: here(url) });
    } catch {
      /* cancelled */
    }
  };
  const rotate = async () => {
    try {
      const { token } = await Api.rotate(id);
      setToken(id, token);
      toast(d.card.rotated, 'ok');
      setConfirm(false);
      onRotated();
    } catch (err) {
      toast(messageOf(err, d.common.error, d.errors), 'bad');
    }
  };
  return (
    <div className="links">
      <p className="section-lead">{d.card.linksBody}</p>
      <ul className="link-list">
        {links.people.map((p) => (
          <li key={p.person_id} className="link-item">
            <QR value={here(p.url)} size={112} label={p.name} />
            <div>
              <strong>{p.name}</strong>
              <div className="row-actions">
                <button type="button" className="btn btn-sm" onClick={() => copy(p.person_id, p.url)}>
                  {copied === p.person_id ? <Check aria-hidden /> : <Copy aria-hidden />}
                  {copied === p.person_id ? d.card.copied : d.card.copy}
                </button>
                {'share' in navigator && (
                  <button type="button" className="btn btn-sm btn-quiet" onClick={() => share(p.name, p.url)}>
                    <Share2 aria-hidden />
                    {d.card.share}
                  </button>
                )}
              </div>
            </div>
          </li>
        ))}
      </ul>
      <div className="danger-zone">
        <p>
          <strong>{d.card.rotate}</strong>
          <span className="help-text"> {d.card.rotateBody}</span>
        </p>
        {confirm ? (
          <div className="row-actions">
            <button type="button" className="btn btn-quiet" onClick={() => setConfirm(false)}>
              {d.common.cancel}
            </button>
            <button type="button" className="btn btn-danger" onClick={rotate}>
              <RefreshCw aria-hidden />
              {d.card.rotateConfirm}
            </button>
          </div>
        ) : (
          <button type="button" className="btn" onClick={() => setConfirm(true)}>
            <RefreshCw aria-hidden />
            {d.card.rotate}
          </button>
        )}
      </div>
    </div>
  );
}

function Offline() {
  const { id, board } = useHousehold();
  const { d, lang } = useI18n();
  const toast = useToast();
  const [progress, setProgress] = useState<[number, number] | null>(null);
  const [saved, setSaved] = useState(() => savedOffline(id));
  if (!offlineSupported()) return <p className="warn-note">{d.card.offlineNo}</p>;
  const save = async () => {
    setProgress([0, 1]);
    try {
      const result = await saveOffline(id, board, (a, b) => setProgress([a, b]));
      setSaved(savedOffline(id));
      if (result.failed === 0) toast(d.card.offlineDone, 'ok');
      else toast(format(d.card.offlinePartial, { saved: result.saved, total: result.total, failed: result.failed }), 'bad');
    } catch (err) {
      toast(messageOf(err, d.common.error, d.errors), 'bad');
    } finally {
      setProgress(null);
    }
  };
  const remove = async () => {
    await forgetOffline(id);
    setSaved(null);
    toast(d.card.offlineRemoved, 'info');
  };
  const partial = !!saved && saved.failed > 0;
  return (
    <div className="offline">
      <p className="section-lead">{d.card.offlineBody}</p>
      <div className="offline-actions">
        <button type="button" className="btn btn-primary" onClick={save} disabled={!!progress}>
          <Download aria-hidden />
          {progress ? `${d.card.saving} ${progress[0]}/${progress[1]}` : d.card.offline}
        </button>
        {saved && !progress && (
          <button type="button" className="btn btn-quiet" onClick={remove}>
            {d.card.offlineRemove}
          </button>
        )}
      </div>
      {saved && !partial && <p className="ok-note">{format(d.card.savedAt, { at: dateTime(saved.at, lang) })}</p>}
      {partial && (
        <p className="warn-note" role="status">
          {format(d.card.offlinePartial, { saved: saved.saved, total: saved.total, failed: saved.failed })} {format(d.card.savedPartialAt, { at: dateTime(saved.at, lang) })}
        </p>
      )}
    </div>
  );
}

export function CardPage() {
  const { id, board } = useHousehold();
  const { d } = useI18n();
  const { search } = useLocation();
  const owner = board.you.role === 'owner';
  const links = useLinks(id, owner);
  const only = search.get('task');
  const tab = ((search.get('tab') as Tab) || (only ? 'stickers' : 'card')) as Tab;
  const setTab = (t: Tab) => navigate(`/h/${id}/card?tab=${t}`, { keepScroll: true, replace: true });
  const stickers = Object.fromEntries((links.data?.stickers ?? []).map((s) => [s.task_key, s.url]));
  const tabs: [Tab, string][] = [
    ['card', d.card.cardTab],
    ...(owner ? ([['stickers', d.card.stickers], ['links', d.card.links]] as [Tab, string][]) : []),
    ['offline', d.card.offlineTab],
  ];
  return (
    <>
      <SampleBanner />
      <PageTitle title={d.card.title} sub={d.card.body} />
      <div className="tabs no-print" role="tablist" aria-label={d.card.title}>
        {tabs.map(([key, label]) => (
          <button key={key} type="button" role="tab" aria-selected={tab === key} onClick={() => setTab(key)}>
            {label}
          </button>
        ))}
      </div>
      {(tab === 'card' || tab === 'stickers') && (
        <div className="print-bar no-print">
          <button type="button" className="btn btn-dark" onClick={() => window.print()}>
            <Printer aria-hidden />
            {d.card.print}
          </button>
          {only && tab === 'stickers' && (
            <button type="button" className="btn btn-quiet" onClick={() => setTab('stickers')}>
              {d.card.allStickers}
            </button>
          )}
        </div>
      )}
      {links.loading && owner ? (
        <Loading />
      ) : links.error ? (
        <ErrorState error={links.error} onRetry={links.reload} />
      ) : (
        <>
          {tab === 'card' && <FridgeCard stickers={stickers} />}
          {tab === 'stickers' && links.data && <Stickers links={links.data} only={only} />}
          {tab === 'links' && links.data && <PeopleLinks links={links.data} onRotated={links.reload} />}
          {tab === 'offline' && <Offline />}
        </>
      )}
    </>
  );
}
