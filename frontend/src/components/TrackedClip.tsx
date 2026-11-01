import { Pause, Play, RotateCcw } from 'lucide-react';
import { lazy, Suspense, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState, type Ref } from 'react';
import { pick, useI18n } from '../i18n';
import { mediaUrl } from '../lib/api';
import { seconds } from '../lib/format';
import { frameAt } from '../lib/mask';
import { canPlay } from '../lib/media';
import type { Clip, Recording, TaskCard } from '../lib/types';
import { ErrorBoundary } from './ErrorBoundary';
import { MaskOverlay } from './MaskOverlay';

const SamClip = lazy(() => import('./SamClip'));

type Caption = { id: string; time: number; text: string; quote: string; kind: 'step' | 'warning' | 'fact' | 'contact' };
export type ClipHandle = { seek: (time: number) => void; current: () => string | null };

/**
 * Plays the owner's own clip for a job, with SAM 3.1's tracked outline drawn over the
 * object frame by frame, and what they said shown as captions in the reader's language.
 */
export function TrackedClip({ household, recording, task, token, ref, onCaption }: { household: string; recording: Recording; task: TaskCard; token?: string | null; ref?: Ref<ClipHandle>; onCaption?: (id: string | null) => void }) {
  const { d, lang } = useI18n();
  const video = useRef<HTMLVideoElement>(null);
  const start = task.clip?.start ?? 0;
  const end = task.clip?.end ?? recording.duration;
  // A job's own clip starts `video_start` seconds into the walk-through; every time here is a
  // walk-through time, so the outlines and captions line up either way.
  const offset = recording.video_start ?? 0;
  const [t, setT] = useState(start);
  const [playing, setPlaying] = useState(false);
  const webm = recording.video_webm ?? null;
  const [failed, setFailed] = useState(() => !recording.video || !(canPlay('mp4') || (!!webm && canPlay('webm'))));
  const [useSam, setUseSam] = useState(false);

  const tracked: Clip | undefined = useMemo(
    () => recording.clips.find((c) => c.claim_id === task.object?.claim_id) ?? recording.clips.find((c) => c.start < end && c.end > start),
    [recording, task, start, end],
  );

  const captions: Caption[] = useMemo(() => {
    const own = (x: { recording_id: string; time: number }) => x.recording_id === recording.id && x.time >= start - 0.5 && x.time <= end + 0.5;
    const items: Caption[] = [
      ...task.facts.filter(own).map((x) => ({ id: x.id, time: x.time, text: pick(x, 'text', lang), quote: x.quote, kind: 'fact' as const })),
      ...task.steps.filter(own).map((x) => ({ id: x.id, time: x.time, text: pick(x, 'text', lang), quote: x.quote, kind: 'step' as const })),
      ...task.warnings.filter(own).map((x) => ({ id: x.id, time: x.time, text: pick(x, 'text', lang), quote: x.quote, kind: 'warning' as const })),
      ...task.contacts.filter(own).map((x) => ({ id: x.id, time: x.time, text: pick(x, 'text', lang), quote: x.quote, kind: 'contact' as const })),
    ];
    return items.sort((a, b) => a.time - b.time);
  }, [task, lang, recording.id, start, end]);

  const caption = useMemo(() => {
    let current: Caption | null = null;
    for (const c of captions) if (c.time <= t + 0.35) current = c;
    return current;
  }, [captions, t]);

  const frame = tracked ? frameAt(tracked.frames, t) : null;
  const staticMask = !tracked && task.object?.mask && Math.abs(t - task.object.time) < 0.6 ? task.object.mask : null;
  const shown = frame ?? staticMask;

  useEffect(() => {
    const v = video.current;
    if (!v || !playing) return;
    let raf = 0;
    const tick = () => {
      setT(v.currentTime + offset);
      if (v.currentTime + offset >= end) {
        v.pause();
        setPlaying(false);
        return;
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playing, end, offset]);

  const play = useCallback(
    async (from?: number) => {
      const v = video.current;
      if (!v) return;
      if (from !== undefined) v.currentTime = Math.max(0, from - offset);
      else if (v.currentTime + offset < start || v.currentTime + offset >= end - 0.05) v.currentTime = Math.max(0, start - offset);
      try {
        await v.play();
        setPlaying(true);
      } catch (err) {
        if ((err as DOMException).name === 'NotAllowedError' && !v.muted) {
          v.muted = true;
          try {
            await v.play();
            setPlaying(true);
            return;
          } catch {
            /* fall through */
          }
        }
        if ((err as DOMException).name !== 'AbortError') setFailed(true);
      }
    },
    [start, end, offset],
  );

  const pause = () => {
    video.current?.pause();
    setPlaying(false);
  };

  const seekTo = (time: number) => {
    setT(time);
    if (!failed) void play(time);
  };

  useImperativeHandle(ref, () => ({ seek: seekTo, current: () => caption?.id ?? null }));
  useEffect(() => {
    onCaption?.(caption?.id ?? null);
  }, [caption, onCaption]);

  // A job's view names its own still as the poster; only the owner's whole recording has poster.jpg.
  const poster = recording.scoped ? (recording.poster ? mediaUrl(household, recording.poster, token) : undefined) : mediaUrl(household, `${recording.id}/poster.jpg`, token);
  const keyframe = task.object?.keyframe_id ? recording.keyframes.find((k) => k.id === task.object!.keyframe_id) : null;
  const still = keyframe ? mediaUrl(household, `${recording.id}/${keyframe.path}`, token) : poster;
  const progress = Math.min(1, Math.max(0, (t - start) / Math.max(0.1, end - start)));
  const spoken = recording.lang;
  const samReady = !!tracked?.sam_text && !!tracked?.clip;
  const ended = t >= end - 0.1;

  return (
    <figure className="clip">
      <div className="clip-stage" style={{ aspectRatio: `${recording.width || 16} / ${recording.height || 9}` }}>
        {useSam && samReady ? (
          <ErrorBoundary fallback={null} onError={() => setUseSam(false)}>
            <Suspense fallback={<div className="clip-loading" />}>
              <SamClip src={mediaUrl(household, tracked!.clip!, token)} samText={tracked!.sam_text!} label={pick(task, 'title', lang)} />
            </Suspense>
          </ErrorBoundary>
        ) : failed ? (
          <>
            {still && <img src={still} alt="" className="clip-media" />}
            {still && task.object?.mask && <MaskOverlay mask={task.object.mask} width={task.object.mask.width} height={task.object.mask.height} fit="contain" trace />}
            <p className="clip-unavailable" role="status">
              {still ? d.task.clipStill : d.task.clipNone}
            </p>
          </>
        ) : (
          <>
            <video
              ref={video}
              className="clip-media"
              src={webm ? undefined : `${mediaUrl(household, recording.video || '', token)}#t=${Math.max(0, start - offset)}`}
              poster={poster}
              playsInline
              preload="metadata"
              aria-label={pick(task, 'title', lang)}
              // With two sources React passes a failed first source's error up to the video, so
              // then only the last source's failure counts.
              onError={webm ? undefined : () => setFailed(true)}
              onPause={() => setPlaying(false)}
              onLoadedMetadata={(e) => {
                if (e.currentTarget.currentTime + offset < start) e.currentTarget.currentTime = Math.max(0, start - offset);
              }}
            >
              {webm && (
                <>
                  <source src={`${mediaUrl(household, recording.video || '', token)}#t=${Math.max(0, start - offset)}`} type="video/mp4" />
                  <source src={`${mediaUrl(household, webm, token)}#t=${Math.max(0, start - offset)}`} type="video/webm" onError={() => setFailed(true)} />
                </>
              )}
            </video>
            {shown && <MaskOverlay mask={shown} width={shown.width} height={shown.height} fit="contain" />}
            {!playing && (
              <button type="button" className="clip-play" onClick={() => void play()} aria-label={d.common.play}>
                {ended ? <RotateCcw aria-hidden /> : <Play aria-hidden />}
              </button>
            )}
          </>
        )}
        {caption && !useSam && (
          <figcaption className="clip-caption" aria-live="polite">
            <span className="clip-caption-text">{caption.text}</span>
            {spoken !== lang && caption.quote && (
              <span className="clip-caption-quote" lang={spoken}>
                “{caption.quote}”
              </span>
            )}
          </figcaption>
        )}
      </div>
      {!failed && !useSam && (
        <div className="clip-bar">
          <button type="button" className="icon-btn" onClick={playing ? pause : () => void play()} aria-label={playing ? d.common.pause : d.common.play}>
            {playing ? <Pause aria-hidden /> : <Play aria-hidden />}
          </button>
          <div className="clip-track" aria-hidden>
            <div className="clip-track-fill" style={{ width: `${progress * 100}%` }} />
            {captions.map((c) => (
              <span key={c.id} className="clip-track-mark" style={{ left: `${((c.time - start) / Math.max(0.1, end - start)) * 100}%` }} />
            ))}
          </div>
          <span className="clip-time">
            {seconds(Math.max(0, t - start))} / {seconds(end - start)}
          </span>
        </div>
      )}
      {samReady && (
        <button type="button" className="btn btn-quiet btn-sm clip-sam-toggle" onClick={() => setUseSam((v) => !v)} aria-pressed={useSam}>
          {d.task.samPlayer}
        </button>
      )}
    </figure>
  );
}
