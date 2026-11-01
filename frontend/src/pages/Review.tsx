import { Check, EarOff, HeartPulse, MessageSquareOff, Pencil, Undo2, X } from 'lucide-react';
import { useMemo, useState } from 'react';
import { EmptyState, ErrorState, Loading, messageOf, useToast } from '../components/Common';
import { MaskOverlay } from '../components/MaskOverlay';
import { PageTitle, SampleBanner, useHousehold } from '../components/Shell';
import { SafetyTag, WitnessList } from '../components/Status';
import { format, pick, useI18n } from '../i18n';
import { Api, mediaUrl } from '../lib/api';
import { seconds } from '../lib/format';
import { useAsync } from '../lib/hooks';
import { useLocation } from '../lib/router';
import type { Claim, Lang, LeftOut, Mask, Recording } from '../lib/types';
import { gateReasons, translateFinding } from '../lib/witness';

type Tab = 'waiting' | 'unused' | 'all';

function requiredFor(c: Claim): ('words' | 'pixels' | 'reading')[] {
  const out: ('words' | 'pixels' | 'reading')[] = ['words'];
  if (c.object_noun) out.push('pixels');
  if (['electricity', 'gas', 'fire'].includes(c.safety)) out.push('reading');
  return out;
}

function ClaimCard({ claim, recording, household, onDecided }: { claim: Claim; recording?: Recording; household: string; onDecided: (c: Claim) => void }) {
  const { d, lang } = useI18n();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(false);
  const [textEn, setTextEn] = useState(claim.text_en);
  const [textSi, setTextSi] = useState(claim.text_si);
  const kf = recording?.keyframes.find((k) => k.id === claim.keyframe_id);
  const words = claim.witnesses.find((w) => w.name === 'words');
  const closest = words?.status === 'fail' ? (words.evidence.closest as string | undefined) : undefined;
  // When the two models disagree there is no agreed mask: show what SAM 3.1 found nearest the point.
  const pixels = claim.witnesses.find((w) => w.name === 'pixels');
  const samMask = claim.mask ?? ((pixels?.evidence.nearest_mask || pixels?.evidence.mask) as Mask | undefined) ?? null;
  const disagree = !claim.mask && !!samMask;
  const decided = claim.status === 'accepted' || claim.status === 'rejected';
  // The family may read the fact in the other language: the owner sees that version too, before
  // accepting it (unless it is only showing her new words, not yet translated).
  const otherLang: Lang = lang === 'si' ? 'en' : 'si';
  const otherText = claim.untranslated?.includes(otherLang) ? '' : (otherLang === 'si' ? claim.text_si : claim.text_en)?.trim() || '';

  const decide = async (decision: 'accepted' | 'rejected') => {
    setBusy(true);
    try {
      const changedEn = textEn !== claim.text_en;
      const changedSi = textSi !== claim.text_si;
      // Only the other language changed: that is a fix to the translation, so the owner's own
      // language, left as it was, is sent too and kept. (A change to her own language is a new
      // instruction: then the other one shows her new words until it is rewritten.)
      const keep = lang === 'en' && changedSi && !changedEn ? { text_en: textEn } : lang === 'si' && changedEn && !changedSi ? { text_si: textSi } : {};
      const edits = editing ? { text_en: changedEn ? textEn : undefined, text_si: changedSi ? textSi : undefined, ...keep } : undefined;
      const { claim: updated } = await Api.decide(household, claim.id, decision, edits);
      onDecided(updated);
      setEditing(false);
      toast(decision === 'accepted' ? d.review.acceptedToast : d.review.rejectedToast, decision === 'accepted' ? 'ok' : 'info');
    } catch (err) {
      toast(messageOf(err, d.common.error, d.errors), 'bad');
    } finally {
      setBusy(false);
    }
  };

  return (
    <article className={`claim claim-${claim.status}`} aria-labelledby={`claim-${claim.id}`}>
      <header className="claim-head">
        <span className="claim-task">{pick(claim, 'title', lang)}</span>
        <span className="claim-kind">{d.kind[claim.kind as keyof typeof d.kind] ?? claim.kind}</span>
        <SafetyTag safety={claim.safety} />
        <span className={`chip claim-status-${claim.status}`}>{d.claimStatus[claim.status]}</span>
        {(claim.edited?.length ?? 0) > 0 && <span className="chip chip-lamp">{d.review.yourWords}</span>}
      </header>
      <div className="claim-main">
        {kf && (
          <div className="claim-frame">
            <img src={mediaUrl(household, `${claim.recording_id}/${kf.path}`)} alt="" loading="lazy" />
            <MaskOverlay mask={samMask} width={kf.width} height={kf.height} point={claim.point} fit="contain" tone={disagree ? 'bad' : 'lamp'} />
            <div className="claim-frame-legend">
              {claim.point && <span className="legend-point">{d.review.point}</span>}
              {samMask && <span className={`legend-mask${disagree ? ' legend-mask-bad' : ''}`}>{disagree ? d.review.maskNearest : d.review.mask}</span>}
            </div>
          </div>
        )}
        <div className="claim-text">
          {editing ? (
            <div className="claim-edit">
              <label className="field">
                <span>English</span>
                <textarea className="textarea" rows={2} value={textEn} onChange={(e) => setTextEn(e.target.value)} lang="en" />
              </label>
              <label className="field">
                <span>සිංහල</span>
                <textarea className="textarea" rows={2} value={textSi} onChange={(e) => setTextSi(e.target.value)} lang="si" />
              </label>
              <p className="help-text">{d.review.editHint}</p>
            </div>
          ) : (
            <>
              <p id={`claim-${claim.id}`} className="claim-statement">
                {pick(claim, 'text', lang)}
              </p>
              {claim.untranslated?.includes(lang) && <p className="help-text claim-untranslated">{d.review.untranslated}</p>}
              {otherText && (
                <div className="claim-other">
                  <span className="label">{d.review.otherLang}</span>
                  <p lang={otherLang}>{otherText}</p>
                </div>
              )}
            </>
          )}
          <div className="claim-quote">
            <span className="label">{d.review.said}</span>
            <blockquote lang={recording?.lang}>“{claim.quote}”</blockquote>
            <span className="help-text">{format(d.task.quoteAt, { t: seconds(claim.time) })}</span>
          </div>
          {closest && (
            <div className="claim-quote claim-closest">
              <span className="label">{d.review.closest}</span>
              <blockquote lang={recording?.lang}>“{closest}”</blockquote>
            </div>
          )}
        </div>
      </div>
      {claim.status === 'blocked' ? (
        <p className="claim-refusal">{translateFinding(claim.blocked_reason, lang)}</p>
      ) : (
        <>
          <WitnessList witnesses={claim.witnesses} required={requiredFor(claim)} />
          {(claim.edited?.length ?? 0) > 0 && <p className="help-text claim-edited-note">{d.review.editedNote}</p>}
        </>
      )}
      {claim.status === 'needs_review' && claim.blocked_reason && (
        <div className="claim-why">
          <p className="label">{d.review.whyTitle}</p>
          <ul>
            {gateReasons(claim.blocked_reason, lang, (n) => (n === 'translation' ? d.review.translation : d.witness[n as 'words'] || n)).map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </div>
      )}
      {claim.status !== 'blocked' && (
        <div className="claim-actions">
          {!decided || editing ? (
            <>
              <button type="button" className="btn btn-quiet" onClick={() => setEditing((v) => !v)} aria-pressed={editing}>
                <Pencil aria-hidden />
                {d.review.edit}
              </button>
              <button type="button" className="btn" onClick={() => decide('rejected')} disabled={busy}>
                <X aria-hidden />
                {d.review.reject}
              </button>
              <button type="button" className="btn btn-ok" onClick={() => decide('accepted')} disabled={busy}>
                <Check aria-hidden />
                {d.review.accept}
              </button>
            </>
          ) : (
            <>
              <button type="button" className="btn btn-quiet" onClick={() => setEditing(true)} aria-pressed={false}>
                <Pencil aria-hidden />
                {d.review.edit}
              </button>
              <button type="button" className="btn btn-quiet" onClick={() => decide(claim.status === 'accepted' ? 'rejected' : 'accepted')} disabled={busy}>
                <Undo2 aria-hidden />
                {claim.status === 'accepted' ? d.review.undoAccept : d.review.undoReject}
              </button>
            </>
          )}
        </div>
      )}
    </article>
  );
}

function LeftOutList({ items }: { items: LeftOut[] }) {
  const { d } = useI18n();
  if (!items.length) return null;
  return (
    <section className="left-out" aria-labelledby="left-out-title">
      <h2 id="left-out-title" className="left-out-title">
        {d.review.leftOutTitle}
      </h2>
      <p className="section-lead">{d.review.leftOutBody}</p>
      <ul className="left-out-list">
        {items.map((t) => (
          <li key={`${t.recording_id}-${t.turn_id}`} className={`left-out-item left-out-${t.reason}`}>
            {t.reason === 'unclear' ? (
              <p className="left-out-unclear">{d.review.leftUnclearQuote}</p>
            ) : (
              <blockquote lang={t.lang}>“{t.text}”</blockquote>
            )}
            <span className="help-text">{format(d.task.quoteAt, { t: seconds(t.start) })}</span>
            <p className="left-out-why">
              {t.reason === 'medical' ? <HeartPulse aria-hidden /> : t.reason === 'unclear' ? <EarOff aria-hidden /> : <MessageSquareOff aria-hidden />}
              <span>{t.reason === 'medical' ? d.review.leftMedical : t.reason === 'unclear' ? d.review.leftUnclear : d.review.leftUnused}</span>
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function ReviewPage() {
  const { id, refresh } = useHousehold();
  const { d } = useI18n();
  const { search } = useLocation();
  const data = useAsync(async () => {
    const c = await Api.claims(id);
    const recs = await Promise.all(Object.keys(c.recordings).map((rid) => Api.recording(id, rid).catch(() => null)));
    return { claims: c.claims, leftOut: c.left_out ?? [], recordings: Object.fromEntries(recs.filter(Boolean).map((r) => [r!.id, r!])) as Record<string, Recording> };
  }, [id]);
  const asked = search.get('show');
  const initial: Tab = asked === 'blocked' || asked === 'unused' ? 'unused' : asked === 'all' ? 'all' : 'waiting';
  const [tab, setTab] = useState<Tab>(initial);
  const [claims, setClaims] = useState<Claim[] | null>(null);
  // Facts decided on this visit stay in place, so the owner sees the result and can undo it.
  const [decidedNow, setDecidedNow] = useState<Set<string>>(() => new Set());
  const all = claims ?? data.data?.claims ?? [];
  const leftOut = data.data?.leftOut ?? [];
  const waiting = all.filter((c) => c.status === 'verified' || c.status === 'needs_review' || decidedNow.has(c.id));
  const blocked = all.filter((c) => c.status === 'blocked');
  const effective: Tab = tab === 'waiting' && waiting.length === 0 && !claims ? 'all' : tab;
  const shown = useMemo(() => (effective === 'waiting' ? waiting : effective === 'unused' ? blocked : all), [effective, waiting, blocked, all]);

  if (data.loading) return <Loading />;
  if (data.error) return <ErrorState error={data.error} onRetry={data.reload} />;
  const onDecided = (c: Claim) => {
    setClaims(all.map((x) => (x.id === c.id ? c : x)));
    setDecidedNow((prev) => new Set(prev).add(c.id));
    void refresh();
  };
  const cards = (list: Claim[]) => (
    <div className="claims">
      {list.map((c) => (
        <ClaimCard key={c.id} claim={c} recording={data.data?.recordings[c.recording_id]} household={id} onDecided={onDecided} />
      ))}
    </div>
  );
  return (
    <>
      <SampleBanner />
      <PageTitle title={d.review.title} sub={d.review.body} />
      <div className="tabs" role="tablist" aria-label={d.review.title}>
        {(
          [
            ['waiting', `${d.review.pending} (${waiting.filter((c) => c.status === 'verified' || c.status === 'needs_review').length})`],
            ['unused', `${d.review.notUsed} (${blocked.length + leftOut.length})`],
            ['all', `${d.review.all} (${all.length})`],
          ] as [Tab, string][]
        ).map(([key, label]) => (
          <button key={key} type="button" role="tab" aria-selected={effective === key} onClick={() => setTab(key)}>
            {label}
          </button>
        ))}
      </div>
      {effective === 'unused' ? (
        blocked.length + leftOut.length === 0 ? (
          <EmptyState text={d.review.none} />
        ) : (
          <>
            {blocked.length > 0 && (
              <>
                <h2 className="left-out-title">{d.review.refusedTitle}</h2>
                {cards(blocked)}
              </>
            )}
            <LeftOutList items={leftOut} />
          </>
        )
      ) : shown.length === 0 ? (
        <EmptyState text={d.review.none} />
      ) : (
        cards(shown)
      )}
    </>
  );
}
