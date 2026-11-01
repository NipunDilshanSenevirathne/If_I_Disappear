import { Camera, CircleCheck, CircleDashed, Film, LoaderCircle, Upload } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { ErrorState, Loading, messageOf } from '../components/Common';
import { PageTitle, SampleBanner, useHousehold } from '../components/Shell';
import { format, useI18n } from '../i18n';
import { Api, mediaUrl, uploadInPieces } from '../lib/api';
import { seconds } from '../lib/format';
import { useAsync } from '../lib/hooks';
import { useHealth } from '../lib/health';
import { Link } from '../lib/router';

const STEPS = ['convert', 'hear', 'privacy', 'read', 'check', 'decide'] as const;

function Pipeline({ done = -1, active = -1, failed = false }: { done?: number; active?: number; failed?: boolean }) {
  const { d } = useI18n();
  return (
    <ol className="pipeline">
      {STEPS.map((s, i) => {
        const state = i <= done ? 'done' : i === active ? (failed ? 'failed' : 'active') : 'todo';
        const Icon = state === 'done' ? CircleCheck : state === 'active' ? LoaderCircle : CircleDashed;
        return (
          <li key={s} className={`pipeline-step pipeline-${state}`}>
            <Icon aria-hidden className={state === 'active' ? 'spin' : undefined} />
            <span>
              <strong>{d.record.steps[s]}</strong>
              <span className="help-text">{d.record.how[s]}</span>
            </span>
          </li>
        );
      })}
    </ol>
  );
}

function SampleRecordings() {
  const { id } = useHousehold();
  const { d } = useI18n();
  const claims = useAsync(() => Api.claims(id), [id]);
  if (claims.loading) return <Loading />;
  if (claims.error) return <ErrorState error={claims.error} onRetry={claims.reload} />;
  const recs = Object.values(claims.data!.recordings).filter((r) => r.kind === 'walkthrough');
  return (
    <div className="rec-list">
      {recs.map((r) => {
        const n = claims.data!.claims.filter((c) => c.recording_id === r.id).length;
        return (
          <article key={r.id} className="rec-card">
            <video src={mediaUrl(id, `${r.id}/video.mp4`)} poster={mediaUrl(id, `${r.id}/poster.jpg`)} controls playsInline preload="none" aria-label={format(d.record.recordingLabel, { lang: d.lang[r.lang as 'en' | 'si'] })} />
            <div className="rec-meta">
              <span className="chip">
                <Film aria-hidden />
                {d.lang[r.lang as 'en' | 'si']}
              </span>
              <span className="help-text">{seconds(r.duration)}</span>
              <span className="help-text">{format(d.record.factsRead, { n })}</span>
            </div>
          </article>
        );
      })}
    </div>
  );
}

function LiveRecorder() {
  const { id, refresh } = useHousehold();
  const { d, lang: uiLang } = useI18n();
  const health = useHealth();
  const [lang, setLang] = useState<'en' | 'si'>(uiLang);
  const [consent, setConsent] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [job, setJob] = useState<string | null>(null);
  const [status, setStatus] = useState<{ done: number; active: number; state: string; error?: string }>({ done: -1, active: -1, state: 'idle' });
  const [error, setError] = useState<string | null>(null);
  const camera = useRef<HTMLInputElement>(null);
  const picker = useRef<HTMLInputElement>(null);
  const sinhalaOff = lang === 'si' && health && !health.sinhala_speech;
  const limitMb = health?.max_upload_mb ?? null;
  const tooBig = !!file && limitMb !== null && file.size > limitMb * 1024 * 1024;

  useEffect(() => () => void (preview && URL.revokeObjectURL(preview)), [preview]);

  useEffect(() => {
    if (!job) return;
    let stop = false;
    const poll = async () => {
      try {
        const j = await Api.job(id, job);
        const names = (j.steps || []).map((s) => s.name);
        const active = names.length ? STEPS.indexOf(names[names.length - 1] as (typeof STEPS)[number]) : 0;
        if (j.status === 'done') {
          setStatus({ done: STEPS.length - 1, active: -1, state: 'done' });
          await refresh();
          return;
        }
        if (j.status === 'failed') {
          setStatus({ done: active - 1, active, state: 'failed', error: (j.code && (d.errors as Record<string, string>)[j.code]) || j.error });
          return;
        }
        setStatus({ done: active - 1, active, state: 'running' });
      } catch {
        /* keep polling */
      }
      if (!stop) window.setTimeout(poll, 1500);
    };
    void poll();
    return () => {
      stop = true;
    };
  }, [id, job, refresh]);

  const choose = (f: File | null) => {
    setError(null);
    setFile(f);
    if (preview) URL.revokeObjectURL(preview);
    setPreview(f ? URL.createObjectURL(f) : null);
  };

  const send = async () => {
    if (!file || !consent || tooBig) return;
    setError(null);
    setProgress(0);
    try {
      const res = await uploadInPieces(id, file, lang, setProgress);
      setProgress(null);
      setJob(res.job_id);
      setStatus({ done: -1, active: 0, state: 'running' });
    } catch (err) {
      setProgress(null);
      setError(messageOf(err, d.common.error, d.errors));
    }
  };

  if (job) {
    return (
      <section className="card">
        <Pipeline done={status.done} active={status.active} failed={status.state === 'failed'} />
        {status.state === 'done' && (
          <div className="row-actions">
            <p className="ok-note">{d.record.done}</p>
            <Link to={`/h/${id}/review`} className="btn btn-primary">
              {d.board.reviewCta}
            </Link>
          </div>
        )}
        {status.state === 'failed' && <p className="error-text">{format(d.record.failed, { error: status.error || '' })}</p>}
      </section>
    );
  }

  return (
    <section className="card record-form">
      <fieldset className="field">
        <legend className="label">{d.record.lang}</legend>
        <div className="seg">
          {(['si', 'en'] as const).map((l) => (
            <button key={l} type="button" aria-pressed={lang === l} onClick={() => setLang(l)} lang={l}>
              {d.lang[l]}
            </button>
          ))}
        </div>
        {sinhalaOff && <p className="warn-note">{d.record.sinhalaOff}</p>}
      </fieldset>
      <p className="help-text">{d.record.tips}</p>
      <input ref={camera} type="file" accept="video/*" capture="environment" hidden onChange={(e) => choose(e.target.files?.[0] ?? null)} />
      <input ref={picker} type="file" accept="video/*" hidden onChange={(e) => choose(e.target.files?.[0] ?? null)} />
      {!file ? (
        <div className="record-choose">
          <button type="button" className="btn btn-primary btn-block" onClick={() => camera.current?.click()}>
            <Camera aria-hidden />
            {d.record.start}
          </button>
          <button type="button" className="btn btn-block" onClick={() => picker.current?.click()}>
            <Upload aria-hidden />
            {d.record.upload}
          </button>
        </div>
      ) : (
        <div className="record-preview">
          {preview && <video src={preview} controls playsInline className="record-video" />}
          <p className="help-text">
            {file.name} ({(file.size / 1024 / 1024).toFixed(1)} MB)
          </p>
          {tooBig && (
            <p className="warn-note" role="alert">
              {format(d.record.tooBig, { size: (file.size / 1024 / 1024).toFixed(1), limit: limitMb ?? '' })}
            </p>
          )}
          <button type="button" className="btn btn-quiet btn-sm" onClick={() => choose(null)}>
            {d.record.another}
          </button>
        </div>
      )}
      <label className="check">
        <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
        <span>{d.record.consent}</span>
      </label>
      {error && <p className="error-text" role="alert">{error}</p>}
      <button type="button" className="btn btn-dark btn-block" disabled={!file || !consent || progress !== null || !!sinhalaOff || tooBig} onClick={send}>
        {progress !== null ? `${d.record.sending} ${Math.round(progress * 100)}%` : d.record.send}
      </button>
    </section>
  );
}

export function RecordPage() {
  const { board } = useHousehold();
  const { d } = useI18n();
  const live = board.mode === 'live' && !board.sample;
  return (
    <>
      <SampleBanner />
      <PageTitle title={d.record.title} sub={d.record.body} />
      {live ? (
        <LiveRecorder />
      ) : (
        <>
          <section className="card note-card">
            <h2>{d.record.sampleTitle}</h2>
            <p>{d.record.sampleBody}</p>
          </section>
          <SampleRecordings />
        </>
      )}
      <section className="section">
        <div className="section-head">
          <h2>{d.record.pipelineTitle}</h2>
        </div>
        <p className="section-lead">{d.record.pipelineBody}</p>
        <Pipeline done={live ? -1 : STEPS.length - 1} />
      </section>
    </>
  );
}
