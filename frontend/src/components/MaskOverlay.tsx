import type { CSSProperties } from 'react';
import { splitMaskPath } from '../lib/mask';
import type { Mask } from '../lib/types';

type Props = {
  mask?: Mask | null;
  /** A path in viewBox units (or "matrix(…)|path", as SAM 3.1 masks are stored), used without a Mask. */
  d?: string;
  width: number;
  height: number;
  /** Muse Spark's point, as a fraction of the frame. */
  point?: [number, number] | null;
  fit?: 'cover' | 'contain';
  tone?: 'lamp' | 'ok' | 'bad';
  trace?: boolean;
  delay?: number;
  className?: string;
  label?: string;
};

/** Draws a SAM 3.1 mask outline (and optionally Muse Spark's point) over a picture or video. */
export function MaskOverlay({ mask, d, width, height, point, fit = 'cover', tone = 'lamp', trace = false, delay = 0, className = '', label }: Props) {
  const shape = mask ? splitMaskPath(mask.path) : d ? splitMaskPath(d) : null;
  const r = Math.max(width, height) * 0.014;
  return (
    <svg
      className={`mask-svg mask-${tone}${trace ? ' mask-trace' : ''} ${className}`}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio={fit === 'cover' ? 'xMidYMid slice' : 'xMidYMid meet'}
      role={label ? 'img' : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      style={trace ? ({ ['--trace-delay' as string]: `${delay}ms` } as CSSProperties) : undefined}
    >
      {shape && (
        <>
          <path className="mask-fill" d={shape.d} transform={shape.transform} />
          <path className="mask-line" d={shape.d} transform={shape.transform} pathLength={1} vectorEffect="non-scaling-stroke" />
        </>
      )}
      {point && (
        <g className="mask-point" transform={`translate(${point[0] * width} ${point[1] * height})`}>
          <circle r={r * 2.2} className="mask-point-halo" />
          <circle r={r} className="mask-point-dot" />
        </g>
      )}
    </svg>
  );
}
