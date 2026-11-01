import { CalendarDays, ChevronRight, CircleCheck, CircleDashed, CircleDot, FileText, GraduationCap, MessageCircleQuestion, ShieldAlert, Wallet, Wrench } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { CoverageChip, SafetyTag } from '../components/Status';
import { MaskOverlay } from '../components/MaskOverlay';
import { Section, messageOf, useToast } from '../components/Common';
import { SampleBanner, useHousehold } from '../components/Shell';
import { format, pick, useI18n } from '../i18n';
import { Api, mediaUrl } from '../lib/api';
import { longDate, scheduleText, shortDate, usd } from '../lib/format';
import { Link } from '../lib/router';
import type { Board as BoardData, Coverage, Gap, TaskCard } from '../lib/types';

const TYPE_ICON: Record<string, typeof Wrench> = { appliance: Wrench, payment: Wallet, document: FileText, schedule: CalendarDays, supply: CircleDot, other: CircleDot };
const ORDER: Coverage[] = ['covered', 'at_risk', 'uncovered', 'unknown'];

export function JobThumb({ task, household }: { task: TaskCard; household: string }) {
  const Icon = TYPE_ICON[task.type] || CircleDot;
  if (task.object?.keyframe_path && task.object.mask) {
    return (
      <div className="job-thumb">
        <img src={mediaUrl(household, task.object.keyframe_path)} alt="" loading="lazy" />
        <MaskOverlay mask={task.object.mask} width={task.object.mask.width} height={task.object.mask.height} />
      </div>
    );
  }
  return (
    <div className={`job-thumb job-thumb-icon job-thumb-${task.coverage}`}>
      <Icon aria-hidden />
    </div>
  );
}

export function PersonDots({ task }: { task: TaskCard }) {
  const { d } = useI18n();
  return (
    <ul className="person-dots">
      {task.people.map((p) => {
        const state = p.proven ? 'proven' : p.show || p.tell ? 'learning' : 'none';
        const Icon = state === 'proven' ? CircleCheck : state === 'learning' ? GraduationCap : CircleDashed;
        return (
          <li key={p.person_id} className={`person-dot person-dot-${state}`}>
            <Icon aria-hidden />
            <span>{p.name}</span>
            <span className="visually-hidden">: {state === 'proven' ? d.board.proven : state === 'learning' ? d.board.learning : d.board.noOne}</span>
          </li>
        );
      })}
    </ul>
  );
}

function JobCard({ task }: { task: TaskCard }) {
  const { id } = useHousehold();
  const { d, lang } = useI18n();
  const when = scheduleText(task.schedule, d, lang);
  return (
    <li>
      <Link to={`/h/${id}/task/${task.key}`} className={`job-card job-card-${task.coverage}`}>
        <JobThumb task={task} household={id} />
        <div className="job-body">
          <h3 className="job-title">{pick(task, 'title', lang)}</h3>
          <div className="job-chips">
            <CoverageChip coverage={task.coverage} />
            <SafetyTag safety={task.safety} />
          </div>
          {(when || task.next) && (
            <p className="job-when">
              {when}
              {task.next && task.schedule?.freq !== 'when_needed' && <span className="job-next">{format(d.board.next, { date: shortDate(task.next, lang) })}</span>}
            </p>
          )}
          <PersonDots task={task} />
        </div>
        <ChevronRight className="job-chevron" aria-hidden />
      </Link>
    </li>
  );
}

function JobStrip({ board }: { board: BoardData }) {
  const { d, lang } = useI18n();
  const tasks = [...board.tasks].sort((a, b) => ORDER.indexOf(a.coverage) - ORDER.indexOf(b.coverage));
  return (
    <div className="job-strip" role="img" aria-label={ORDER.filter((c) => board.counts[c]).map((c) => `${board.counts[c]} ${d.status[c]}`).join(', ')}>
      {tasks.map((t) => (
        <span key={t.key} className={`job-strip-seg seg-${t.coverage}`} title={`${pick(t, 'title', lang)}: ${d.status[t.coverage]}`} />
      ))}
    </div>
  );
}

function Headline({ board }: { board: BoardData }) {
  const { d, lang } = useI18n();
  const name = board.leaving?.name;
  const { stop_tomorrow: n, total } = board.headline;
  const absence = board.household.absence;
  const first = board.simulation.first_stop;
  const firstTask = first ? board.tasks.find((t) => t.key === first.task_key) : null;
  return (
    <section className="board-hero" aria-labelledby="board-title">
      <h1 id="board-title" className="board-hero-title">
        {name ? format(d.board.titleLeaving, { name }) : d.board.titleNoName}
      </h1>
      <p className="board-hero-stat">{total === 0 ? d.board.empty : n === 0 ? d.board.allGood : format(d.board.stops, { n, total })}</p>
      {total > 0 && <JobStrip board={board} />}
      <ul className="board-legend">
        {ORDER.filter((c) => board.counts[c]).map((c) => (
          <li key={c}>
            <span className={`legend-swatch seg-${c}`} aria-hidden />
            {board.counts[c]} {d.status[c]}
          </li>
        ))}
      </ul>
      {absence && (
        <dl className="board-dates">
          <div>
            <dt>{d.board.leavesLabel}</dt>
            <dd>{longDate(absence.start, lang)}</dd>
          </div>
          <div>
            <dt>{d.board.backLabel}</dt>
            <dd>{longDate(absence.end, lang)}</dd>
          </div>
          <div>
            <dt>{d.board.daysLabel}</dt>
            <dd>{board.plan.days_available}</dd>
          </div>
        </dl>
      )}
      {first && firstTask && (
        <p className="board-first">
          <ShieldAlert aria-hidden />
          <span>{format(d.board.firstStop, { date: longDate(first.date, lang), job: pick(firstTask, 'title', lang) })}</span>
        </p>
      )}
    </section>
  );
}

function Plan({ board }: { board: BoardData }) {
  const { id, minutes, setMinutes } = useHousehold();
  const { d, lang } = useI18n();
  const names = Object.fromEntries(board.people.map((p) => [p.id, p.name]));
  const titles = Object.fromEntries(board.tasks.map((t) => [t.key, pick(t, 'title', lang)]));
  const days = board.plan.days.slice(0, 5);
  return (
    <Section
      id="plan"
      title={d.board.plan}
      action={
        <label className="inline-select">
          <span>{d.board.minutesPerDay}</span>
          <select className="select" value={minutes} onChange={(e) => setMinutes(Number(e.target.value))}>
            {[10, 20, 30, 45, 60].map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </label>
      }
    >
      <p className="section-lead">{format(d.board.planBody, { minutes: format(d.common.minutes, { n: minutes }) })}</p>
      {days.length === 0 ? (
        <p className="empty-note">{d.board.planNone}</p>
      ) : (
        <ol className="plan">
          {days.map((day, i) => (
            <li key={day.date} className="plan-day">
              <div className="plan-day-head">
                <strong>{i === 0 && day.date === board.today ? d.common.today : longDate(day.date, lang)}</strong>
                <span>{format(d.common.minutes, { n: day.minutes })}</span>
              </div>
              <ul>
                {day.sessions.map((s) => (
                  <li key={`${s.person_id}-${s.task_key}`}>
                    <Link to={`/h/${id}/prove?task=${s.task_key}&person=${s.person_id}`} className="plan-session">
                      <span className="plan-who">{names[s.person_id]}</span>
                      <span className="plan-what">{titles[s.task_key]}</span>
                      <span className={`chip ${s.why === 'safety' ? 'chip-bad' : ''}`}>{d.why[s.why as keyof typeof d.why] ?? s.why}</span>
                      <span className="plan-min">{format(d.common.minutes, { n: s.minutes })}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ol>
      )}
      {board.plan.unscheduled.length > 0 && <p className="warn-note">{format(d.board.unscheduled, { n: board.plan.unscheduled.length })}</p>}
    </Section>
  );
}

function GapItem({ gap }: { gap: Gap }) {
  const { id, board, refresh } = useHousehold();
  const { d, lang } = useI18n();
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const owner = board.you.role === 'owner';
  const task = board.tasks.find((t) => t.key === gap.task_key);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!text.trim()) return;
    setBusy(true);
    try {
      const form = new FormData();
      form.set('task_key', gap.task_key);
      form.set('slot', gap.slot);
      form.set('lang', lang);
      form.set('text', text.trim());
      await Api.answerGap(id, form);
      toast(d.board.answered, 'ok');
      await refresh();
    } catch (err) {
      toast(messageOf(err, d.common.error, d.errors), 'bad');
    } finally {
      setBusy(false);
    }
  };
  return (
    <li className="gap">
      <div className="gap-head">
        <MessageCircleQuestion aria-hidden />
        <div>
          <p className="gap-q">{lang === 'si' ? gap.question_si : gap.question_en}</p>
          {task && <p className="gap-task">{pick(task, 'title', lang)}</p>}
        </div>
        {owner && !open && (
          <button type="button" className="btn btn-sm" onClick={() => setOpen(true)}>
            {d.board.answer}
          </button>
        )}
      </div>
      {open && (
        <form className="gap-form" onSubmit={submit}>
          <label className="field">
            <span>{d.board.answerLabel}</span>
            <textarea className="textarea" value={text} onChange={(e) => setText(e.target.value)} rows={3} required maxLength={600} />
          </label>
          <p className="help-text">{d.board.answerNote}</p>
          <div className="row-actions">
            <button type="button" className="btn btn-quiet" onClick={() => setOpen(false)}>
              {d.common.cancel}
            </button>
            <button type="submit" className="btn btn-dark" disabled={busy || !text.trim()}>
              {busy ? <span className="spinner" aria-hidden /> : null}
              {d.common.save}
            </button>
          </div>
        </form>
      )}
    </li>
  );
}

type Bar = { key: string; label: string; covered: number; at_risk: number; uncovered: number; unknown: number };

/** A long absence is drawn a month to a bar, so two years still fit on a phone. */
function bars(weeks: BoardData['simulation']['weeks'], lang: 'en' | 'si'): { bars: Bar[]; monthly: boolean } {
  if (weeks.length <= 60) return { bars: weeks.map((w) => ({ key: w.week_start, label: shortDate(w.week_start, lang), ...w })), monthly: false };
  const months = new Map<string, Bar>();
  for (const w of weeks) {
    const key = w.week_start.slice(0, 7);
    const m = months.get(key) ?? { key, label: shortDate(`${key}-01`, lang), covered: 0, at_risk: 0, uncovered: 0, unknown: 0 };
    m.covered += w.covered;
    m.at_risk += w.at_risk;
    m.uncovered += w.uncovered;
    m.unknown += w.unknown;
    months.set(key, m);
  }
  return { bars: [...months.values()], monthly: true };
}

function Timeline({ board }: { board: BoardData }) {
  const { d, lang } = useI18n();
  const sim = board.simulation;
  if (!sim.weeks.length) return null;
  const { bars: list, monthly } = bars(sim.weeks, lang);
  const max = Math.max(1, ...list.map((w) => w.covered + w.at_risk + w.uncovered + w.unknown));
  const bad = list.filter((w) => w.uncovered + w.at_risk > 0).length;
  const body = monthly ? format(d.board.timelineBodyMonths, { months: list.length, bad }) : format(d.board.timelineBody, { weeks: list.length, bad });
  const back = sim.asked_end ?? sim.end;
  return (
    <Section id="timeline" title={monthly ? d.board.timelineMonths : d.board.timeline}>
      <p className="section-lead">{body}</p>
      <div className={`timeline${monthly ? ' timeline-months' : ''}`} role="img" aria-label={body}>
        {list.map((w) => (
          <div key={w.key} className="timeline-week" title={`${w.label}: ${w.covered} ${d.status.covered}, ${w.at_risk} ${d.status.at_risk}, ${w.uncovered} ${d.status.uncovered}`}>
            <div className="timeline-bar" style={{ height: `${((w.covered + w.at_risk + w.uncovered + w.unknown) / max) * 100}%` }}>
              {w.uncovered > 0 && <span className="seg-uncovered" style={{ flexGrow: w.uncovered }} />}
              {w.at_risk > 0 && <span className="seg-at_risk" style={{ flexGrow: w.at_risk }} />}
              {w.unknown > 0 && <span className="seg-unknown" style={{ flexGrow: w.unknown }} />}
              {w.covered > 0 && <span className="seg-covered" style={{ flexGrow: w.covered }} />}
            </div>
          </div>
        ))}
      </div>
      <div className="timeline-axis" aria-hidden>
        <span>{list[0].label}</span>
        <span>{list[list.length - 1].label}</span>
      </div>
      <p className="help-text timeline-horizon">
        {sim.capped ? format(d.board.simulatedCapped, { date: longDate(sim.end, lang), back: longDate(back, lang) }) : format(d.board.simulatedTo, { date: longDate(sim.end, lang) })}
      </p>
    </Section>
  );
}

export function BoardPage() {
  const { id, board } = useHousehold();
  const { d } = useI18n();
  const pending = board.review.verified + board.review.needs_review;
  const owner = board.you.role === 'owner';
  return (
    <>
      <SampleBanner />
      <Headline board={board} />
      {owner && pending > 0 && (
        <Link to={`/h/${id}/review`} className="review-cta">
          <span>
            <strong>{pending === 1 ? d.board.reviewOne : format(d.board.review, { n: pending })}</strong>
            <span className="help-text">{d.review.body}</span>
          </span>
          <span className="btn btn-primary btn-sm">{d.board.reviewCta}</span>
        </Link>
      )}
      <Section id="jobs" title={d.board.jobs} action={board.review.blocked + (board.review.left_out ?? 0) > 0 && owner ? <Link to={`/h/${id}/review?show=unused`} className="link-quiet">{board.review.blocked + (board.review.left_out ?? 0) === 1 ? d.board.blockedNoteOne : format(d.board.blockedNote, { n: board.review.blocked + (board.review.left_out ?? 0) })}</Link> : undefined}>
        {board.tasks.length === 0 ? (
          <div className="empty-card">
            <p>{d.board.noJobs}</p>
            {owner && (
              <Link to={`/h/${id}/record`} className="btn btn-primary">
                {d.record.start}
              </Link>
            )}
          </div>
        ) : (
          <ul className="job-list">
            {board.tasks.map((t) => (
              <JobCard key={t.key} task={t} />
            ))}
          </ul>
        )}
      </Section>
      {owner && <Plan board={board} />}
      {board.gaps.length > 0 && (
        <Section id="gaps" title={d.board.gaps}>
          <p className="section-lead">{d.board.gapsBody}</p>
          <ul className="gaps">
            {board.gaps.map((g) => (
              <GapItem key={`${g.task_key}-${g.slot}`} gap={g} />
            ))}
          </ul>
        </Section>
      )}
      <Timeline board={board} />
      <footer className="board-foot">
        {owner ? (
          <Link to={`/h/${id}/evidence`} className="board-foot-link">
            {format(d.board.ledger, { n: board.ledger.events })}
            <code>{board.ledger.head.slice(0, 12)}</code>
          </Link>
        ) : (
          <span className="board-foot-link">
            {format(d.board.ledger, { n: board.ledger.events })}
            <code>{board.ledger.head.slice(0, 12)}</code>
          </span>
        )}
        <span>{format(d.board.costs, { usd: usd(board.costs_usd) })}</span>
      </footer>
    </>
  );
}
