import { BadgeCheck, CircleCheck, CircleDashed, CircleX, History, Printer } from 'lucide-react';
import { useCallback, useRef, useState } from 'react';
import { ErrorState } from '../components/Common';
import { JobDetails } from '../components/JobDetails';
import { SampleBanner, useHousehold } from '../components/Shell';
import { CoverageChip, SafetyTag } from '../components/Status';
import { TrackedClip, type ClipHandle } from '../components/TrackedClip';
import { format, pick, useI18n } from '../i18n';
import { Api } from '../lib/api';
import { longDate, scheduleText } from '../lib/format';
import { useAsync } from '../lib/hooks';
import { Link } from '../lib/router';
import type { TaskCard } from '../lib/types';

function ProofMark({ value, label }: { value: boolean | null; label: string }) {
  const Icon = value === true ? CircleCheck : value === false ? CircleX : CircleDashed;
  return (
    <span className={`proof-mark proof-mark-${value === true ? 'ok' : value === false ? 'bad' : 'none'}`}>
      <Icon aria-hidden />
      {label}
    </span>
  );
}

export function WhoCan({ task, household }: { task: TaskCard; household: string }) {
  const { d, lang } = useI18n();
  const needsShow = !!task.object;
  return (
    <section className="detail-block who-can">
      <h2>{d.task.whoCan}</h2>
      <ul>
        {task.people.map((p) => (
          <li key={p.person_id} className={p.proven ? 'is-proven' : ''}>
            <span className="who-name">{p.name}</span>
            <span className="who-marks">
              {needsShow && <ProofMark value={p.show} label={d.task.show} />}
              <ProofMark value={p.tell} label={d.task.tell} />
            </span>
            {p.proven && p.proven_until ? (
              <span className="help-text">{format(d.task.until, { date: longDate(p.proven_until, lang) })}</span>
            ) : p.stale && p.stale.length > 0 ? (
              <span className="who-stale">
                <span className="help-text">{p.stale.includes('tell') ? d.task.staleTell : d.task.staleShow}</span>
                <Link to={`/h/${household}/prove?task=${task.key}&person=${p.person_id}`} className="btn btn-sm">
                  {d.task.proveAgain}
                </Link>
              </span>
            ) : (
              <Link to={`/h/${household}/prove?task=${task.key}&person=${p.person_id}`} className="btn btn-sm">
                {d.task.prove}
              </Link>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

export function TaskPage({ taskKey }: { taskKey: string }) {
  const { id, board } = useHousehold();
  const { d, lang } = useI18n();
  const task = board.tasks.find((t) => t.key === taskKey);
  const clipRef = useRef<ClipHandle>(null);
  const [current, setCurrent] = useState<string | null>(null);
  const recId = task?.clip?.recording_id ?? task?.object?.recording_id ?? null;
  // The job's own view: what a family member gets, so the owner sees the same clip they do.
  const rec = useAsync(() => (recId && task ? Api.recording(id, recId, undefined, task.key) : Promise.resolve(null)), [id, recId, task?.key]);
  const onCaption = useCallback((cid: string | null) => setCurrent(cid), []);

  if (!task) return <ErrorState error={new Error(d.task.missing)} />;
  const when = scheduleText(task.schedule, d, lang);
  const owner = board.leaving?.name ?? '';
  return (
    <>
      <SampleBanner />
      <div className="task-head">
        <h1>{pick(task, 'title', lang)}</h1>
        <div className="job-chips">
          <CoverageChip coverage={task.coverage} />
          <SafetyTag safety={task.safety} />
        </div>
        {when && <p className="task-when">{when}</p>}
      </div>
      {recId && (
        <section className="task-clip" aria-label={format(d.task.clip, { name: owner })}>
          <p className="task-clip-label">{format(d.task.clip, { name: owner })}</p>
          {rec.loading ? <div className="clip-skeleton" /> : rec.error ? <ErrorState error={rec.error} onRetry={rec.reload} /> : rec.data ? <TrackedClip ref={clipRef} household={id} recording={rec.data} task={task} onCaption={onCaption} /> : null}
        </section>
      )}
      {!recId && <p className="empty-note">{d.task.noClip}</p>}
      <JobDetails task={task} spoken={rec.data?.lang} onSeek={rec.data ? (t) => clipRef.current?.seek(t) : undefined} current={current} clipRecording={recId} owner={owner} />
      <WhoCan task={task} household={id} />
      <div className="task-actions">
        <Link to={`/h/${id}/prove?task=${task.key}`} className="btn btn-primary">
          <BadgeCheck aria-hidden />
          {d.task.prove}
        </Link>
        <Link to={`/h/${id}/card?task=${task.key}`} className="btn">
          <Printer aria-hidden />
          {d.task.sticker}
        </Link>
        {board.you.role === 'owner' && (
          <Link to={`/h/${id}/evidence?task=${task.key}`} className="btn btn-quiet">
            <History aria-hidden />
            {d.task.evidence}
          </Link>
        )}
      </div>
    </>
  );
}
