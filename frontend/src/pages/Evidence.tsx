import { Bot, CircleCheck, CircleX, Code2, FlaskConical, Link2, User } from 'lucide-react';
import { useMemo, useState } from 'react';
import { ErrorState, Loading } from '../components/Common';
import { PageTitle, SampleBanner, useHousehold } from '../components/Shell';
import { format, useI18n } from '../i18n';
import type { Dict } from '../i18n/en';
import { Api } from '../lib/api';
import { dateTime } from '../lib/format';
import { useAsync } from '../lib/hooks';
import { useLocation } from '../lib/router';
import type { LedgerEvent, Lang } from '../lib/types';
import { actorKind, modelName, translateFinding } from '../lib/witness';

type Filter = 'all' | 'model' | 'code' | 'person';
const ACTOR_ICON = { model: Bot, recorded: Bot, sample: FlaskConical, code: Code2, person: User, system: Code2 };

function str(v: unknown): string {
  return typeof v === 'string' ? v : v == null ? '' : String(v);
}

type Names = { people: Record<string, string>; tasks: Record<string, string>; claims: Record<string, string> };

function summary(e: LedgerEvent, d: Dict, lang: Lang, n: Names): string {
  const names = n.people;
  const claim = (id: unknown) => (n.claims[str(id)] ? `“${n.claims[str(id)]}”` : str(id));
  const task = (k: unknown) => n.tasks[str(k)] || str(k);
  const p = e.payload as Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
  const ev = d.events;
  switch (e.type) {
    case 'household.created':
      return format(ev.created, { name: str(p.household?.name) });
    case 'person.added':
      return format(ev.personAdded, { name: str(p.person?.name) });
    case 'person.updated':
      return format(ev.personUpdated, { name: str(p.person?.name) });
    case 'person.removed':
      return format(ev.personRemoved, { name: names[p.person_id] || str(p.person_id) });
    case 'absence.set':
      return format(ev.absence, { start: str(p.absence?.start), end: str(p.absence?.end) });
    case 'recording.added':
      return format(ev.recording, { lang: d.lang[(p.recording?.lang as 'en' | 'si') || 'en'] });
    case 'recording.keyframes':
      return format(ev.keyframes, { n: (p.keyframes || []).length });
    case 'recording.transcribed':
      return format(ev.transcribed, { n: Array.isArray(p.turns) ? p.turns.length : 0, engine: str(p.engine) || e.actor.replace(/^(model|sample):/, '') });
    case 'recording.redacted':
      return format(ev.redacted, { n: (p.redactions || []).length });
    case 'claims.proposed':
      return format(ev.proposed, { n: (p.claims || []).length });
    case 'claim.masked':
      return format(ev.masked, { claim: claim(p.claim_id) });
    case 'witness.recorded': {
      const w = p.witness || {};
      return `${format(ev.witness, { claim: claim(p.claim_id), witness: d.witness[w.name as 'words'] || str(w.name), status: d.witness[w.status as 'pass'] || str(w.status) })} ${translateFinding(str(w.detail), lang)}`;
    }
    case 'claim.gated':
      return format(ev.gated, { claim: claim(p.claim_id), status: d.claimStatus[p.status as 'verified'] || str(p.status) });
    case 'claim.decided':
      return format(p.decision === 'accepted' ? ev.accepted : ev.rejected, { claim: claim(p.claim_id) });
    case 'clip.tracked':
      return format(ev.tracked, { n: (p.frames || []).length, claim: claim(p.claim_id) });
    case 'clip.track_failed':
      return format(ev.trackFailed, { claim: claim(p.claim_id), why: str(p.error) });
    case 'proof.recorded': {
      const pr = p.proof || {};
      return format(pr.passed ? ev.proofPass : ev.proofFail, { name: names[pr.person_id] || str(pr.person_id), kind: d.proofKind[pr.kind as 'show'] || str(pr.kind), task: task(pr.task_key) });
    }
    case 'help.asked':
      return format(ev.asked, { q: str(p.question) });
    case 'help.answered':
      return p.task_key ? format(ev.answered, { task: task(p.task_key) }) : ev.notAnswered;
    case 'gap.answered':
      return format(ev.gap, { task: task(p.task_key) });
    case 'cost.recorded':
      return format(ev.cost, { model: str(p.model), usd: Number(p.usd || 0).toFixed(4) });
    case 'links.rotated':
      return ev.rotated;
    case 'job.updated':
      return format(ev.job, { status: str(p.status), step: str(p.step?.name) });
    default:
      return e.type;
  }
}

function relatedTo(e: LedgerEvent, task: string, claimIds: Set<string>): boolean {
  const p = e.payload as Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
  if (p.task_key === task || p.proof?.task_key === task) return true;
  if (p.claim_id && claimIds.has(p.claim_id)) return true;
  if (e.type === 'claims.proposed') return (p.claims || []).some((c: { task_key: string }) => c.task_key === task);
  return false;
}

export function EvidencePage() {
  const { id, board } = useHousehold();
  const { d, lang } = useI18n();
  const { search } = useLocation();
  const task = search.get('task');
  const data = useAsync(() => Api.evidence(id, 2000), [id]);
  const [filter, setFilter] = useState<Filter>('all');
  const names: Names = useMemo(() => {
    const claims: Record<string, string> = {};
    for (const e of data.data?.events ?? []) {
      if (e.type === 'claims.proposed')
        for (const c of ((e.payload as { claims?: { id: string; text_en: string; text_si: string }[] }).claims ?? [])) claims[c.id] = lang === 'si' && c.text_si ? c.text_si : c.text_en;
    }
    return {
      people: Object.fromEntries(board.people.map((p) => [p.id, p.name])),
      tasks: Object.fromEntries(board.tasks.map((t) => [t.key, lang === 'si' && t.title_si ? t.title_si : t.title_en])),
      claims,
    };
  }, [data.data, board, lang]);

  const claimIds = useMemo(() => {
    const ids = new Set<string>();
    for (const e of data.data?.events ?? []) {
      if (e.type === 'claims.proposed') for (const c of ((e.payload as { claims?: { id: string; task_key: string }[] }).claims ?? [])) if (c.task_key === task) ids.add(c.id);
    }
    return ids;
  }, [data.data, task]);

  if (data.loading) return <Loading />;
  if (data.error) return <ErrorState error={data.error} onRetry={data.reload} />;
  const all = [...data.data!.events].reverse();
  const shown = all.filter((e) => {
    const kind = actorKind(e.actor);
    if (task && !relatedTo(e, task, claimIds)) return false;
    if (filter === 'model') return kind === 'model' || kind === 'recorded' || kind === 'sample';
    if (filter === 'code') return kind === 'code' || kind === 'system';
    if (filter === 'person') return kind === 'person';
    return true;
  });
  const taskTitle = task ? board.tasks.find((t) => t.key === task) : null;

  return (
    <>
      <SampleBanner />
      <PageTitle title={d.evidence.title} sub={d.evidence.body} />
      <div className={`chain chain-${data.data!.chain_ok ? 'ok' : 'bad'}`} role="status">
        {data.data!.chain_ok ? <CircleCheck aria-hidden /> : <CircleX aria-hidden />}
        <span>
          {data.data!.chain_ok ? format(d.evidence.intact, { n: data.data!.count }) : format(d.evidence.broken, { n: data.data!.broken_at ?? '?' })}
          <code className="chain-head">
            <Link2 aria-hidden /> {board.ledger.head.slice(0, 16)}…
          </code>
        </span>
      </div>
      {taskTitle && <p className="filter-note">{format(d.evidence.forJob, { job: lang === 'si' ? taskTitle.title_si || taskTitle.title_en : taskTitle.title_en })}</p>}
      <div className="tabs" role="tablist" aria-label={d.evidence.filter}>
        {(
          [
            ['all', d.evidence.all],
            ['model', d.evidence.models],
            ['code', d.evidence.code],
            ['person', d.evidence.people],
          ] as [Filter, string][]
        ).map(([key, label]) => (
          <button key={key} type="button" role="tab" aria-selected={filter === key} onClick={() => setFilter(key)}>
            {label}
          </button>
        ))}
      </div>
      <ol className="ledger">
        {shown.map((e) => {
          const kind = actorKind(e.actor);
          const Icon = ACTOR_ICON[kind];
          return (
            <li key={e.seq} className={`ledger-row ledger-${kind}`}>
              <span className="ledger-seq">#{e.seq}</span>
              <div className="ledger-body">
                <p className="ledger-summary">{summary(e, d, lang, names)}</p>
                <p className="ledger-meta">
                  <span className={`chip ledger-actor ledger-actor-${kind}`}>
                    <Icon aria-hidden />
                    {kind === 'sample'
                      ? format(d.evidence.sampleActor, { who: modelName(e.actor) })
                      : kind === 'recorded'
                        ? format(d.evidence.recordedActor, { who: modelName(e.actor) })
                        : kind === 'person'
                          ? e.actor === 'owner'
                            ? d.evidence.owner
                            : e.actor
                          : kind === 'model'
                            ? modelName(e.actor)
                            : e.actor}
                  </span>
                  <time dateTime={e.at}>{dateTime(e.at, lang)}</time>
                  <code title={e.digest}>{e.digest.slice(0, 10)}</code>
                </p>
              </div>
            </li>
          );
        })}
      </ol>
    </>
  );
}
