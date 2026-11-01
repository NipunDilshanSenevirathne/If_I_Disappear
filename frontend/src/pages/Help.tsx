import { Bot, ChevronRight, Code2, Mic, Phone, Send, Siren, Square } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { EmergencyNumbers, messageOf, Section, useToast } from '../components/Common';
import { PageTitle, SampleBanner, useHousehold } from '../components/Shell';
import { CoverageChip, SafetyTag } from '../components/Status';
import { format, pick, useI18n } from '../i18n';
import { Api } from '../lib/api';
import { useRecorder } from '../lib/hooks';
import { Link } from '../lib/router';
import type { HelpResult, Lang } from '../lib/types';
import { modelName } from '../lib/witness';

const SAMPLE_QUESTIONS: { text: string; lang: Lang }[] = [
  { text: 'කරන්ට් ගියා, මොකද කරන්නේ?', lang: 'si' },
  { text: 'The pump is making a grinding noise', lang: 'en' },
  { text: 'Where are the house deed papers?', lang: 'en' },
  { text: 'ගෑස් ඉවර වුණා', lang: 'si' },
  { text: 'When do I pay the electricity bill?', lang: 'en' },
  { text: 'How do I fix the washing machine?', lang: 'en' },
  { text: 'I can smell gas in the kitchen', lang: 'en' },
];

function detectLang(text: string): Lang {
  return /[඀-෿]/.test(text) ? 'si' : 'en';
}

function DecidedBy({ result }: { result: HelpResult }) {
  const { d, lang } = useI18n();
  const by = result.decided_by;
  const who = by === 'code' ? d.help.code : by.startsWith('replay:') ? format(d.help.replay, { model: modelName(by) }) : modelName(by);
  const reason = lang === 'si' ? result.reason_si || result.reason : result.reason;
  return (
    <p className="decided-by">
      {by === 'code' ? <Code2 aria-hidden /> : <Bot aria-hidden />}
      <span>
        {format(d.help.decidedBy, { who })}
        {reason && <span className="decided-reason"> {reason}</span>}
      </span>
    </p>
  );
}

function Contacts({ result }: { result: HelpResult }) {
  const { d, lang } = useI18n();
  if (!result.contacts.length) return null;
  return (
    <div className="help-contacts">
      <p className="label">{d.help.callThese}</p>
      <ul className="contacts">
        {result.contacts.map((c) => (
          <li key={c.name}>
            <Phone aria-hidden />
            <span>
              <strong>{c.name}</strong>
              {c.role && <span className="help-text"> {c.role}</span>}
              <span className="contact-said">{lang === 'si' ? c.for_si || c.for : c.for}</span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Answer({ result }: { result: HelpResult }) {
  const { id, board } = useHousehold();
  const { d, lang } = useI18n();
  const owner = board.leaving?.name ?? '';
  if (result.emergency) {
    return (
      <section className="answer answer-emergency" role="alert">
        <h2>
          <Siren aria-hidden />
          {d.help.emergency}
        </h2>
        <p>{d.help.emergencyBody}</p>
        <EmergencyNumbers />
        <Contacts result={result} />
        <DecidedBy result={result} />
      </section>
    );
  }
  if (result.medical) {
    // Decided by code: medicine is never recorded here, so no job can answer this.
    return (
      <section className="answer answer-none answer-medical" role="status">
        <h2>{d.help.medical}</h2>
        <p>{d.help.medicalBody}</p>
        <EmergencyNumbers compact />
        <DecidedBy result={result} />
      </section>
    );
  }
  const task = result.task;
  if (!task) {
    return (
      <section className="answer answer-none">
        <h2>{format(d.help.notRecorded, { name: owner })}</h2>
        <Contacts result={result} />
        <DecidedBy result={result} />
      </section>
    );
  }
  return (
    <section className="answer">
      <p className="answer-kicker">{format(d.help.recorded, { name: owner })}</p>
      <h2>{pick(task, 'title', lang)}</h2>
      <div className="job-chips">
        <CoverageChip coverage={task.coverage} />
        <SafetyTag safety={task.safety} />
      </div>
      {task.steps.length > 0 && (
        <ol className="steps steps-compact">
          {task.steps.map((s) => (
            <li key={s.id}>{pick(s, 'text', lang)}</li>
          ))}
        </ol>
      )}
      {task.warnings.length > 0 && (
        <ul className="careful-list">
          {task.warnings.map((w) => (
            <li key={w.id}>{pick(w, 'text', lang)}</li>
          ))}
        </ul>
      )}
      {task.contacts.length > 0 && (
        <ul className="contacts">
          {task.contacts.map((c) => (
            <li key={c.id}>
              <Phone aria-hidden />
              <span>
                <strong>{c.name}</strong> <span className="help-text">{c.role}</span>
              </span>
            </li>
          ))}
        </ul>
      )}
      <Link to={`/h/${id}/task/${task.key}`} className="btn btn-dark">
        {format(d.help.watch, { name: owner })}
        <ChevronRight aria-hidden />
      </Link>
      <DecidedBy result={result} />
    </section>
  );
}

function renderWhatsApp(text: string) {
  return text.split('\n').map((line, i) => {
    const parts = line.split(/(\*[^*]+\*|https?:\/\/\S+)/g).filter(Boolean);
    return (
      <span key={i} className="wa-line">
        {parts.map((p, j) =>
          p.startsWith('*') && p.endsWith('*') ? (
            <strong key={j}>{p.slice(1, -1)}</strong>
          ) : /^https?:\/\//.test(p) ? (
            <a key={j} href={new URL(p).pathname + new URL(p).search} className="wa-link">
              {p.length > 48 ? `${p.slice(0, 45)}…` : p}
            </a>
          ) : (
            <span key={j}>{p}</span>
          ),
        )}
      </span>
    );
  });
}

function WhatsAppPreview() {
  const { id, board } = useHousehold();
  const { d, lang } = useI18n();
  const toast = useToast();
  const staying = board.people.filter((p) => p.role !== 'leaving');
  const [person, setPerson] = useState(board.you.role === 'person' ? board.you.person_id || '' : staying.find((p) => p.language === 'si')?.id || staying[0]?.id || '');
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [chat, setChat] = useState<{ from: 'me' | 'them'; text: string; lang?: Lang }[]>([]);
  const send = async (e?: FormEvent, preset?: string) => {
    e?.preventDefault();
    const q = (preset ?? text).trim();
    if (!q || !person) return;
    const qLang = detectLang(q);
    setChat((c) => [...c, { from: 'me', text: q, lang: qLang }]);
    setText('');
    setBusy(true);
    try {
      const res = await Api.simulate(id, person, q, qLang);
      setChat((c) => [...c, ...res.replies.map((r) => ({ from: 'them' as const, text: r, lang: qLang }))]);
    } catch (err) {
      toast(messageOf(err, d.common.error, d.errors), 'bad');
    } finally {
      setBusy(false);
    }
  };
  return (
    <Section id="whatsapp" title={d.help.simulator}>
      <p className="section-lead">{d.help.simulatorBody}</p>
      <div className="wa">
        <div className="wa-top">
          <span className="wa-avatar" aria-hidden>
            IID
          </span>
          <span>
            <strong>If I Disappear</strong>
            <span className="wa-sub">{board.household.name}</span>
          </span>
          {board.you.role === 'owner' && (
            <label className="wa-as">
              <span className="visually-hidden">{d.help.from}</span>
              <select className="select" value={person} onChange={(e) => setPerson(e.target.value)} aria-label={d.help.from}>
                {staying.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>
        <div className="wa-body" aria-live="polite">
          {chat.length === 0 && (
            <div className="wa-hints">
              {[lang === 'si' ? 'කරන්ට් ගියා, මොකද කරන්නේ?' : 'The power went off, what do I do?', 'ගෑස් ඉවර වුණා'].map((q) => (
                <button key={q} type="button" className="chip-btn" onClick={() => void send(undefined, q)} lang={detectLang(q)}>
                  {q}
                </button>
              ))}
            </div>
          )}
          {chat.map((m, i) => (
            <p key={i} className={`wa-msg wa-${m.from}`} lang={m.lang}>
              {renderWhatsApp(m.text)}
            </p>
          ))}
          {busy && <p className="wa-msg wa-them wa-typing">…</p>}
        </div>
        <form className="wa-input" onSubmit={send}>
          <label className="visually-hidden" htmlFor="wa-text">
            {d.help.placeholder}
          </label>
          <input id="wa-text" className="input" value={text} onChange={(e) => setText(e.target.value)} placeholder={d.help.placeholder} autoComplete="off" />
          <button type="submit" className="icon-btn wa-send" aria-label={d.help.send} disabled={busy || !text.trim()}>
            <Send aria-hidden />
          </button>
        </form>
      </div>
    </Section>
  );
}

export function HelpPage() {
  const { id, board } = useHousehold();
  const { d, lang } = useI18n();
  const toast = useToast();
  const rec = useRecorder();
  const [question, setQuestion] = useState('');
  const [asked, setAsked] = useState('');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<HelpResult | null>(null);
  const live = board.mode === 'live' && !board.sample;

  const ask = async (q: string) => {
    const text = q.trim();
    if (!text) return;
    setBusy(true);
    setAsked(text);
    try {
      const r = await Api.help(id, text, detectLang(text));
      // Show the question as it was kept: a PIN or password in it comes back as [hidden].
      setAsked(r.question || text);
      setResult(r);
    } catch (err) {
      toast(messageOf(err, d.common.error, d.errors), 'bad');
    } finally {
      setBusy(false);
    }
  };

  const askByVoice = async () => {
    if (rec.state === 'recording') {
      const blob = await rec.stop();
      if (!blob) return;
      setBusy(true);
      try {
        const f = new FormData();
        f.set('audio', blob, 'question.webm');
        f.set('lang', lang);
        const r = await Api.helpVoice(id, f);
        setAsked(r.question || '');
        setResult(r);
      } catch (err) {
        toast(messageOf(err, d.common.error, d.errors), 'bad');
      } finally {
        setBusy(false);
      }
    } else {
      await rec.start();
    }
  };

  const suggestions = board.sample ? SAMPLE_QUESTIONS : board.tasks.slice(0, 6).map((t) => ({ text: pick(t, 'title', lang), lang }));

  return (
    <>
      <SampleBanner />
      <PageTitle title={d.help.title} sub={d.help.body} />
      <EmergencyNumbers compact />
      <form
        className="ask"
        onSubmit={(e) => {
          e.preventDefault();
          void ask(question);
        }}
      >
        <label htmlFor="ask" className="visually-hidden">
          {d.help.placeholder}
        </label>
        <input id="ask" className="input ask-input" value={question} onChange={(e) => setQuestion(e.target.value)} placeholder={d.help.placeholder} autoComplete="off" lang={detectLang(question)} />
        <button type="submit" className="btn btn-primary" disabled={busy || !question.trim()}>
          {busy ? <span className="spinner" aria-hidden /> : null}
          {d.help.ask}
        </button>
        {live && rec.supported && (
          <button type="button" className={`btn ${rec.state === 'recording' ? 'btn-danger' : ''}`} onClick={askByVoice} disabled={busy}>
            {rec.state === 'recording' ? <Square aria-hidden /> : <Mic aria-hidden />}
            {rec.state === 'recording' ? `${d.record.stop} (${rec.seconds}s)` : d.help.voice}
          </button>
        )}
      </form>
      {rec.state === 'denied' && (
        <p className="error-text" role="alert">
          {d.help.micDenied}
        </p>
      )}
      <div className="suggest">
        <span className="label">{d.help.suggestions}</span>
        <ul>
          {suggestions.map((s) => (
            <li key={s.text}>
              <button
                type="button"
                className="chip-btn"
                lang={s.lang}
                onClick={() => {
                  setQuestion(s.text);
                  void ask(s.text);
                }}
              >
                {s.text}
              </button>
            </li>
          ))}
        </ul>
      </div>
      {asked && result && (
        <div className="asked">
          <p className="asked-q" lang={detectLang(asked)}>
            “{asked}”
          </p>
          <Answer result={result} />
        </div>
      )}
      <WhatsAppPreview />
    </>
  );
}
