import { parseVideoStream, type ResponsesEvent, type VideoSegmentationResult } from '@meta-sam/parser';
import { Video, type VideoRef } from '@meta-sam/react';
import { Pause, Play } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { useI18n } from '../i18n';

/** Replays stored SAM 3.1 output text as the Responses events the parser reads. */
async function* events(text: string): AsyncIterable<ResponsesEvent> {
  yield { type: 'response.output_text.delta', item_id: 'sam', output_index: 0, content_index: 0, delta: text } as ResponsesEvent;
  yield { type: 'response.output_text.done', item_id: 'sam', output_index: 0, content_index: 0, text } as ResponsesEvent;
  yield { type: 'response.completed' } as ResponsesEvent;
}

/**
 * Meta's own SAM player (@meta-sam/react) for clips tracked live by SAM 3.1. It decodes
 * the clip with WebCodecs and draws the masks itself. Used only when the browser can.
 */
export default function SamClip({ src, samText, label }: { src: string; samText: string; label: string }) {
  const { d } = useI18n();
  const ref = useRef<VideoRef>(null);
  const [result, setResult] = useState<VideoSegmentationResult | null>(null);
  const [playing, setPlaying] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    let live = true;
    const parsed = parseVideoStream(events(samText));
    (async () => {
      for await (const _snapshot of parsed) {
        void _snapshot;
      }
      const final = await parsed.finalResult;
      if (live) setResult(final);
    })().catch((e: Error) => live && setError(e));
    return () => {
      live = false;
    };
  }, [samText]);

  if (error) throw error;
  if (!result) return <div className="clip-loading" />;
  return (
    <div className="sam-clip">
      <Video
        ref={ref}
        src={src}
        result={result}
        objectFit="contain"
        devicePixelRatio={() => window.devicePixelRatio || 1}
        onPlayingChange={setPlaying}
        onError={(e) => setError(e)}
        canvasProps={{ 'aria-label': label, role: 'img' }}
        style={{ width: '100%', height: '100%' }}
      />
      <button type="button" className="clip-play" onClick={() => (playing ? ref.current?.pause() : void ref.current?.play())} aria-label={playing ? d.common.pause : d.common.play}>
        {playing ? <Pause aria-hidden /> : <Play aria-hidden />}
      </button>
    </div>
  );
}
