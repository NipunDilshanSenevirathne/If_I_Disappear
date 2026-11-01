import { useCallback, useEffect, useRef, useState } from 'react';
import { EmergencyNumbers, ErrorState, Loading } from '../components/Common';
import { JobDetails } from '../components/JobDetails';
import { Logo } from '../components/Logo';
import { LangToggle } from '../components/Shell';
import { SafetyTag } from '../components/Status';
import { TrackedClip, type ClipHandle } from '../components/TrackedClip';
import { format, pick, useI18n } from '../i18n';
import { Api, ApiError, setToken } from '../lib/api';
import { savedSticker } from '../lib/offline';
import { useAsync } from '../lib/hooks';
import { Link, navigate } from '../lib/router';
import type { Household, TaskCard } from '../lib/types';

function StickerView({ token, householdId, household, task, saved }: { token: string; householdId: string; household: Pick<Household, 'name'>; task: TaskCard; saved?: boolean }) {
  const { d, lang } = useI18n();
  const clip = useRef<ClipHandle>(null);
  const [current, setCurrent] = useState<string | null>(null);
  const recId = task.clip?.recording_id ?? task.object?.recording_id ?? null;
  // The link's own household id: a sample home's copy keeps the sample's id inside its data.
  const rec = useAsync(() => (recId ? Api.recording(householdId, recId, token, task.key).catch(() => null) : Promise.resolve(null)), [householdId, recId, token, task.key]);
  const onCaption = useCallback((c: string | null) => setCurrent(c), []);
  return (
    <div className="sticker-page">
      <header className="sticker-top">
        <Logo light size={28} />
        <LangToggle dark />
      </header>
      {saved && <p className="offline-bar">{d.common.offline}</p>}
      <main id="main" className="sticker-main">
        <p className="help-text">{household.name}</p>
        <h1>{pick(task, 'title', lang)}</h1>
        <SafetyTag safety={task.safety} />
        {rec.loading ? (
          <div className="clip-skeleton" />
        ) : rec.data ? (
          <TrackedClip ref={clip} household={householdId} recording={rec.data} task={task} token={token} onCaption={onCaption} />
        ) : recId ? (
          <p className="clip-unavailable clip-unavailable-alone" role="status">
            {saved ? d.link.clipNotSaved : d.task.clipNone}
          </p>
        ) : null}
        <JobDetails task={task} spoken={rec.data?.lang} onSeek={rec.data ? (t) => clip.current?.seek(t) : undefined} current={current} clipRecording={recId} />
        <section className="detail-block">
          <h2>{d.help.emergencyShort}</h2>
          <EmergencyNumbers />
        </section>
      </main>
    </div>
  );
}

export function LinkOpenPage({ token }: { token: string }) {
  const { d } = useI18n();
  const [state, setState] = useState<{ kind: 'loading' } | { kind: 'error'; error: Error; offline?: boolean } | { kind: 'sticker'; householdId: string; household: Pick<Household, 'name'>; task: TaskCard; saved?: boolean }>({ kind: 'loading' });

  useEffect(() => {
    let live = true;
    Api.openLink(token)
      .then((res) => {
        if (!live) return;
        if (res.kind === 'sticker') {
          if (!res.task || !res.household) throw new ApiError(404, d.link.invalid);
          setState({ kind: 'sticker', householdId: res.household_id, household: res.household, task: res.task });
          return;
        }
        setToken(res.household_id, res.token);
        const task = new URLSearchParams(location.search).get('task');
        navigate(task ? `/h/${res.household_id}/task/${encodeURIComponent(task)}` : `/h/${res.household_id}`, { replace: true });
      })
      .catch(async (error: Error) => {
        // No connection: a sticker still opens its job if this phone saved the offline pack.
        const offline = error instanceof ApiError && error.status === 0;
        const saved = offline ? await savedSticker(token) : null;
        if (!live) return;
        setState(saved ? { kind: 'sticker', householdId: saved.householdId, household: saved.household, task: saved.task, saved: true } : { kind: 'error', error, offline });
      });
    return () => {
      live = false;
    };
  }, [token, d.link.invalid]);

  if (state.kind === 'loading') return <Loading label={d.link.opening} />;
  if (state.kind === 'error') {
    const gone = state.error instanceof ApiError && (state.error.status === 410 || state.error.status === 404 || state.error.status === 401);
    return (
      <div className="center-page">
        <Logo />
        {gone ? (
          <p className="state">{d.link.invalid}</p>
        ) : state.offline ? (
          <div className="state">
            <p>{d.link.offlineNotSaved}</p>
            <p className="help-text">{d.link.offlineHow}</p>
          </div>
        ) : (
          <ErrorState error={state.error} />
        )}
        <Link to="/" className="btn">
          {d.link.home}
        </Link>
      </div>
    );
  }
  return <StickerView token={token} householdId={state.householdId} household={state.household} task={state.task} saved={state.saved} />;
}

export function TryPage() {
  const { d } = useI18n();
  const [error, setError] = useState<Error | null>(null);
  const started = useRef(false);
  const start = useCallback(() => {
    setError(null);
    Api.startDemo()
      .then(({ household_id, token }) => {
        setToken(household_id, token);
        navigate(`/h/${household_id}`, { replace: true });
      })
      .catch((e: Error) => setError(e));
  }, []);
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    start();
  }, [start]);
  if (error)
    return (
      <div className="center-page">
        <Logo />
        <ErrorState error={error} onRetry={start} />
      </div>
    );
  return (
    <div className="center-page">
      <Logo />
      <Loading label={d.try.opening} />
      <p className="help-text center-note">{format(d.try.note, {})}</p>
    </div>
  );
}
