import { Camera, CircleCheck, CircleX, Keyboard, Mic, Square, Timer } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { EmptyState, messageOf, useToast } from '../components/Common';
import { MaskOverlay } from '../components/MaskOverlay';
import { PageTitle, SampleBanner, useHousehold } from '../components/Shell';
import { CoverageChip, SafetyTag } from '../components/Status';
import { format, pick, useI18n } from '../i18n';
import { Api, mediaUrl } from '../lib/api';
import { longDate } from '../lib/format';
import { useAsync, useRecorder } from '../lib/hooks';
import { navigate, useLocation } from '../lib/router';
import type { ProofResult, TaskCard } from '../lib/types';

type Samples = Awaited<ReturnType<typeof Api.samples>>;

function Verdict({ result, kind }: { result: ProofResult; kind: 'show' | 'tell' }) {
  const { d, lang } = useI18n();
  const reasons = lang === 'si' && result.reasons_si?.length ? result.reasons_si : result.reasons_en;
  const ev = result.evidence;
  const explanation = lang === 'si' ? ev.explanation_si || ev.explanation_en : ev.explanation_en;
  return (
    <div className={`verdict verdict-${result.passed ? 'pass' : 'fail'}`} role="status">
      <p className="verdict-head">
        {result.passed ? <CircleCheck aria-hidden /> : <CircleX aria-hidden />}
        <strong>{result.passed ? d.prove.passed : result.outcome === 'cannot_verify' ? d.prove.unsure : d.prove.failed}</strong>
        {typeof ev.seconds === 'number' && <span className="chip">{format(d.prove.seconds, { n: Math.round(ev.seconds as number) })}</span>}
      </p>
      <ul className="verdict-reasons">
        {reasons.map((r, i) => (
          <li key={i}>{r}</li>
        ))}
      </ul>
      {kind === 'show' && explanation && <p className="verdict-why">{explanation}</p>}
      {kind === 'show' && ev.matched && ev.matched.length > 0 && (
        <div className="verdict-list">
          <span className="label">{d.prove.matched}</span>
          <ul>
            {ev.matched.map((m) => (
              <li key={m}>{m}</li>
            ))}
          </ul>
        </div>
      )}
      {kind === 'show' && ev.mismatches && ev.mismatches.length > 0 && (
        <div className="verdict-list">
          <span className="label">{d.prove.different}</span>
          <ul>
            {ev.mismatches.map((m) => (
              <li key={m}>{m}</li>
            ))}
          </ul>
        </div>
      )}
      {kind === 'tell' && ev.points && (
        <ul className="points">
          {ev.points.map((p) => {
            const ok = p.verified ?? p.covered;
            return (
              <li key={p.point_id} className={ok ? 'point-ok' : 'point-miss'}>
                {ok ? <CircleCheck aria-hidden /> : <CircleX aria-hidden />}
                <span>
                  <span className="point-text">
                    {lang === 'si' ? p.text_si || p.text_en : p.text_en}
                    {p.safety && <span className="chip chip-bad point-safety">{d.prove.safetyStep}</span>}
                  </span>
                  {ok && p.quote && (
                    <span className="point-quote" lang={ev.lang}>
                      “{p.quote}”
                    </span>
                  )}
                </span>
              </li>
            );
          })}
        </ul>
      )}
      {kind === 'tell' && ev.transcript && (
        <details className="transcript">
          <summary>{d.prove.transcript}</summary>
          <p lang={ev.lang}>{ev.transcript}</p>
        </details>
      )}
    </div>
  );
}

function ShowMe({ task, personId, samples, sample, onDone }: { task: TaskCard; personId: string; samples: Samples['show']; sample: boolean; onDone: () => void }) {
  const { id } = useHousehold();
  const { d, lang } = useI18n();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ProofResult | null>(null);
  const [photo, setPhoto] = useState<string | null>(null);
  const [drill, setDrill] = useState<number | null>(null);
  const [left, setLeft] = useState(60);
  const input = useRef<HTMLInputElement>(null);
  const mine = samples.filter((s) => s.task_key === task.key);

  useEffect(() => {
    if (drill === null) return;
    const t = window.setInterval(() => setLeft(Math.max(0, 60 - Math.round((Date.now() - drill) / 1000))), 250);
    return () => window.clearInterval(t);
  }, [drill]);

  const submit = async (form: FormData, shownPhoto: string | null) => {
    setBusy(true);
    setResult(null);
    form.set('task_key', task.key);
    form.set('person_id', personId);
    if (drill !== null) form.set('seconds', String(Math.round((Date.now() - drill) / 1000)));
    try {
      const r = await Api.show(id, form);
      if (drill !== null) r.evidence.seconds = Number(form.get('seconds'));
      setResult(r);
      setPhoto(r.evidence.photo ? mediaUrl(id, r.evidence.photo) : shownPhoto);
      setDrill(null);
      onDone();
    } catch (err) {
      toast(messageOf(err, d.common.error, d.errors), 'bad');
    } finally {
      setBusy(false);
    }
  };

  const trySample = (sid: string, path: string | null) => {
    const f = new FormData();
    f.set('sample_id', sid);
    void submit(f, path ? mediaUrl(id, path) : null);
  };

  const takePhoto = (file: File | null) => {
    if (!file) return;
    const f = new FormData();
    f.set('photo', file);
    void submit(f, URL.createObjectURL(file));
  };

  const mask = result?.evidence.mask;
  return (
    <section className="card proof-card" aria-labelledby="show-title">
      <h2 id="show-title">{format(d.prove.showTitle, { thing: lang === 'en' && task.object?.noun ? task.object.noun : pick(task, 'title', lang) })}</h2>
      <p className="help-text">{d.prove.showBody}</p>
      {task.safety === 'electricity' && !result && (
        <div className="drill">
          <Timer aria-hidden />
          <span>
            <strong>{d.prove.drill}</strong> {d.prove.drillBody}
          </span>
          {drill === null ? (
            <button type="button" className="btn btn-sm" onClick={() => (setLeft(60), setDrill(Date.now()))}>
              {d.prove.start}
            </button>
          ) : (
            <span className={`drill-clock${left <= 10 ? ' is-low' : ''}`} aria-live="polite">
              {format(d.prove.seconds, { n: left })}
            </span>
          )}
        </div>
      )}
      <div className="proof-actions">
        {!sample && (
          <>
            <input ref={input} type="file" accept="image/*" capture="environment" hidden onChange={(e) => takePhoto(e.target.files?.[0] ?? null)} />
            <button type="button" className="btn btn-primary" onClick={() => input.current?.click()} disabled={busy}>
              <Camera aria-hidden />
              {d.prove.takePhoto}
            </button>
          </>
        )}
      </div>
      {sample && mine.length > 0 && (
        <div className="sample-picks">
          <p className="label">{d.prove.samplePhotos}</p>
          <ul>
            {mine.map((s) => (
              <li key={s.id}>
                <button type="button" className="sample-photo" onClick={() => trySample(s.id, s.photo)} disabled={busy} aria-label={format(d.prove.useSample, { n: s.id })}>
                  {s.photo && <img src={mediaUrl(id, s.photo)} alt="" loading="lazy" />}
                  <span>{s.id.endsWith('wrong') ? d.prove.sampleOther : d.prove.sampleRight}</span>
                </button>
              </li>
            ))}
          </ul>
          <p className="help-text">{d.prove.liveOnly}</p>
        </div>
      )}
      {busy && (
        <p className="busy-line" role="status">
          <span className="spinner" aria-hidden /> {d.prove.checking}
        </p>
      )}
      {result && (
        <div className="proof-result">
          {photo && (
            <div className="proof-photo">
              <img src={photo} alt="" />
              {mask && <MaskOverlay mask={mask} width={mask.width} height={mask.height} fit="contain" tone={result.passed ? 'ok' : 'bad'} trace />}
            </div>
          )}
          <Verdict result={result} kind="show" />
        </div>
      )}
    </section>
  );
}

function TellMe({ task, personId, samples, sample, onDone }: { task: TaskCard; personId: string; samples: Samples['tell']; sample: boolean; onDone: () => void }) {
  const { id } = useHousehold();
  const { d, lang } = useI18n();
  const toast = useToast();
  const rec = useRecorder();
  const [typing, setTyping] = useState(false);
  const [text, setText] = useState('');
  const [answerLang, setAnswerLang] = useState<'en' | 'si'>(lang);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ProofResult | null>(null);
  const mine = samples.filter((s) => s.task_key === task.key).sort((a, b) => Number(b.person_id === personId) - Number(a.person_id === personId));

  const submit = async (form: FormData) => {
    setBusy(true);
    setResult(null);
    form.set('task_key', task.key);
    form.set('person_id', personId);
    if (!form.has('lang')) form.set('lang', answerLang);
    try {
      setResult(await Api.tell(id, form));
      onDone();
    } catch (err) {
      toast(messageOf(err, d.common.error, d.errors), 'bad');
    } finally {
      setBusy(false);
    }
  };

  const stopAndSend = async () => {
    const blob = await rec.stop();
    if (!blob) return;
    const f = new FormData();
    f.set('audio', blob, `answer.${blob.type.includes('mp4') ? 'm4a' : 'webm'}`);
    void submit(f);
  };

  return (
    <section className="card proof-card" aria-labelledby="tell-title">
      <h2 id="tell-title">{d.prove.tellTitle}</h2>
      <p className="help-text">{d.prove.tellBody}</p>
      {!sample && (
        <>
          <div className="seg seg-sm" role="group" aria-label={d.record.lang}>
            {(['si', 'en'] as const).map((l) => (
              <button key={l} type="button" aria-pressed={answerLang === l} onClick={() => setAnswerLang(l)} lang={l}>
                {d.lang[l]}
              </button>
            ))}
          </div>
          <div className="proof-actions">
            {rec.state === 'recording' ? (
              <button type="button" className="btn btn-danger" onClick={stopAndSend}>
                <Square aria-hidden />
                {d.record.stop} ({rec.seconds}s)
              </button>
            ) : (
              <button type="button" className="btn btn-primary" onClick={rec.start} disabled={busy || !rec.supported}>
                <Mic aria-hidden />
                {d.prove.speak}
              </button>
            )}
            <button type="button" className="btn" onClick={() => setTyping((v) => !v)} aria-expanded={typing}>
              <Keyboard aria-hidden />
              {d.prove.type}
            </button>
          </div>
          {rec.state === 'denied' && <p className="error-text">{d.prove.micDenied}</p>}
          {typing && (
            <form
              className="tell-form"
              onSubmit={(e) => {
                e.preventDefault();
                const f = new FormData();
                f.set('text', text);
                void submit(f);
              }}
            >
              <label className="field">
                <span>{d.prove.typeLabel}</span>
                <textarea className="textarea" rows={4} value={text} onChange={(e) => setText(e.target.value)} lang={answerLang} required />
              </label>
              <button type="submit" className="btn btn-dark" disabled={busy || !text.trim()}>
                {d.prove.check}
              </button>
            </form>
          )}
        </>
      )}
      {sample && mine.length > 0 && (
        <div className="sample-answers">
          <p className="label">{d.prove.sampleAnswers}</p>
          <ul>
            {mine.map((s) => (
              <li key={s.id}>
                <button
                  type="button"
                  className="sample-answer"
                  disabled={busy}
                  onClick={() => {
                    const f = new FormData();
                    f.set('sample_id', s.id);
                    f.set('lang', s.lang);
                    void submit(f);
                  }}
                >
                  <span className="sample-answer-text" lang={s.lang}>
                    “{s.transcript}”
                  </span>
                  <span className="chip">{d.lang[s.lang]}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
      {sample && mine.length === 0 && <p className="help-text">{d.prove.noSampleAnswer}</p>}
      {busy && (
        <p className="busy-line" role="status">
          <span className="spinner" aria-hidden /> {d.prove.checking}
        </p>
      )}
      {result && <Verdict result={result} kind="tell" />}
    </section>
  );
}

export function ProvePage() {
  const { id, board, refresh } = useHousehold();
  const { d, lang } = useI18n();
  const { search } = useLocation();
  const samples = useAsync(() => Api.samples(id), [id]);
  const staying = board.people.filter((p) => p.role !== 'leaving');
  const lockedPerson = board.you.role === 'person' ? board.you.person_id : null;
  const personId = lockedPerson || search.get('person') || '';
  const taskKey = search.get('task') || '';
  const task = board.tasks.find((t) => t.key === taskKey);
  const person = staying.find((p) => p.id === personId);
  const before = useRef(task?.coverage);
  const [celebrate, setCelebrate] = useState(false);

  const setParam = (k: string, v: string) => {
    const s = new URLSearchParams(location.search);
    s.set(k, v);
    navigate(`/h/${id}/prove?${s.toString()}`, { keepScroll: true });
  };

  useEffect(() => {
    before.current = task?.coverage;
    setCelebrate(false);
  }, [taskKey]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (task && before.current && before.current !== 'covered' && task.coverage === 'covered') setCelebrate(true);
  }, [task, task?.coverage]);

  const status = useMemo(() => (task && person ? task.people.find((p) => p.person_id === person.id) : null), [task, person]);
  const sample = board.sample;
  const onDone = () => void refresh();

  return (
    <>
      <SampleBanner />
      <PageTitle title={d.prove.title} sub={d.prove.body} />
      {!lockedPerson && (
        <section className="pick" aria-labelledby="pick-person">
          <h2 id="pick-person" className="pick-title">
            {d.prove.who}
          </h2>
          <div className="pick-row">
            {staying.map((p) => (
              <button key={p.id} type="button" className="pick-chip" aria-pressed={p.id === personId} onClick={() => setParam('person', p.id)}>
                {p.name}
                {p.relation && <span className="help-text">{p.relation}</span>}
              </button>
            ))}
          </div>
        </section>
      )}
      <section className="pick" aria-labelledby="pick-task">
        <h2 id="pick-task" className="pick-title">
          {d.prove.which}
        </h2>
        <div className="pick-jobs">
          {board.tasks.map((t) => {
            const st = person ? t.people.find((p) => p.person_id === person.id) : null;
            return (
              <button key={t.key} type="button" className="pick-job" aria-pressed={t.key === taskKey} onClick={() => setParam('task', t.key)}>
                <span className="pick-job-title">{pick(t, 'title', lang)}</span>
                <span className="pick-job-meta">
                  <CoverageChip coverage={t.coverage} compact />
                  {st?.proven && <span className="chip chip-ok">{d.board.proven}</span>}
                </span>
              </button>
            );
          })}
        </div>
      </section>
      {!task || !person ? (
        <EmptyState text={!person ? d.prove.pickPerson : d.prove.pickJob} />
      ) : (
        <div className="proof-area">
          <div className="proof-summary">
            <div>
              <h2>
                {person.name}: {pick(task, 'title', lang)}
              </h2>
              <div className="job-chips">
                <CoverageChip coverage={task.coverage} />
                <SafetyTag safety={task.safety} />
              </div>
            </div>
            {status?.proven && status.proven_until && <p className="ok-note">{format(d.task.until, { date: longDate(status.proven_until, lang) })}</p>}
          </div>
          {celebrate && (
            <div className="celebrate" role="status">
              <CircleCheck aria-hidden />
              <span>{format(d.prove.nowCovered, { job: pick(task, 'title', lang) })}</span>
            </div>
          )}
          {task.object ? (
            <ShowMe key={`show-${task.key}-${person.id}`} task={task} personId={person.id} samples={samples.data?.show ?? []} sample={sample} onDone={onDone} />
          ) : (
            <p className="help-text">{d.prove.noObject}</p>
          )}
          <TellMe key={`tell-${task.key}-${person.id}`} task={task} personId={person.id} samples={samples.data?.tell ?? []} sample={sample} onDone={onDone} />
        </div>
      )}
    </>
  );
}
