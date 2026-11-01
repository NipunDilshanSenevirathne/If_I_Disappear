import { Phone, Play, StickyNote, TriangleAlert } from 'lucide-react';
import { pick, useI18n, format } from '../i18n';
import { seconds } from '../lib/format';
import type { Lang, TaskCard } from '../lib/types';

type Props = { task: TaskCard; spoken?: Lang; onSeek?: (time: number) => void; current?: string | null; clipRecording?: string | null; owner?: string };

function SaidAt({ time, onSeek, recording, item }: { time: number; onSeek?: (t: number) => void; recording?: string | null; item: { recording_id?: string } }) {
  const { d } = useI18n();
  if (!onSeek || (recording && item.recording_id && item.recording_id !== recording)) return null;
  return (
    <button type="button" className="said-at" onClick={() => onSeek(time)} aria-label={format(d.task.playFrom, { t: seconds(time) })}>
      <Play aria-hidden />
      {seconds(time)}
    </button>
  );
}

function Quote({ text, spoken }: { text: string; spoken?: Lang }) {
  const { lang } = useI18n();
  if (!text || !spoken || spoken === lang) return null;
  return (
    <span className="item-quote" lang={spoken}>
      “{text}”
    </span>
  );
}

/** The job written out: steps in order, then cautions, contacts, facts and typed notes. */
export function JobDetails({ task, spoken, onSeek, current, clipRecording, owner }: Props) {
  const { d, lang } = useI18n();
  return (
    <div className="job-details">
      {task.steps.length > 0 && (
        <section className="detail-block">
          <h2>{d.task.steps}</h2>
          <ol className="steps">
            {task.steps.map((s) => (
              <li key={s.id} className={current === s.id ? 'is-current' : ''}>
                <span className="step-text">
                  {pick(s, 'text', lang)}
                  <Quote text={s.quote} spoken={spoken} />
                </span>
                <SaidAt time={s.time} onSeek={onSeek} recording={clipRecording} item={s} />
              </li>
            ))}
          </ol>
        </section>
      )}
      {task.warnings.length > 0 && (
        <section className="detail-block detail-careful">
          <h2>
            <TriangleAlert aria-hidden />
            {d.task.careful}
          </h2>
          <ul>
            {task.warnings.map((w) => (
              <li key={w.id} className={current === w.id ? 'is-current' : ''}>
                <span className="step-text">
                  {pick(w, 'text', lang)}
                  <Quote text={w.quote} spoken={spoken} />
                </span>
                <SaidAt time={w.time} onSeek={onSeek} recording={clipRecording} item={w} />
              </li>
            ))}
          </ul>
        </section>
      )}
      {task.contacts.length > 0 && (
        <section className="detail-block">
          <h2>{d.task.call}</h2>
          <ul className="contacts">
            {task.contacts.map((c) => (
              <li key={c.id}>
                <Phone aria-hidden />
                <span>
                  <strong>{c.name}</strong>
                  {c.role && <span className="help-text"> {c.role}</span>}
                  <span className="contact-said">{pick(c, 'text', lang)}</span>
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
      {task.facts.length > 0 && (
        <section className="detail-block">
          <h2>{d.task.facts}</h2>
          <ul>
            {task.facts.map((f) => (
              <li key={f.id} className={current === f.id ? 'is-current' : ''}>
                <span className="step-text">
                  {pick(f, 'text', lang)}
                  <Quote text={f.quote} spoken={spoken} />
                </span>
                <SaidAt time={f.time} onSeek={onSeek} recording={clipRecording} item={f} />
              </li>
            ))}
          </ul>
        </section>
      )}
      {task.notes.length > 0 && (
        <section className="detail-block detail-notes">
          <h2>
            <StickyNote aria-hidden />
            {format(d.task.notes, { name: owner || '' })}
          </h2>
          <ul>
            {task.notes.map((n, i) => (
              <li key={i}>
                <span className="step-text">{n.text}</span>
              </li>
            ))}
          </ul>
          <p className="help-text">{d.task.notesNote}</p>
        </section>
      )}
    </div>
  );
}
