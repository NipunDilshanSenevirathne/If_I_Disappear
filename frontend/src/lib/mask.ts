import type { Mask } from './types';

/** A mask path is stored as "matrix(a b c d e f)|M x y L ..." in media pixels. */
export function splitMaskPath(path: string): { transform?: string; d: string } {
  const bar = path.indexOf('|');
  if (bar < 0) return { d: path };
  return { transform: path.slice(0, bar).trim(), d: path.slice(bar + 1).trim() };
}

/** Pick the tracked frame nearest to time t (seconds), or null if t is outside the clip. */
export function frameAt<T extends { t: number }>(frames: T[], t: number, tolerance = 0.25): T | null {
  if (!frames.length) return null;
  if (t < frames[0].t - tolerance || t > frames[frames.length - 1].t + tolerance) return null;
  let lo = 0;
  let hi = frames.length - 1;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (frames[mid].t < t) lo = mid + 1;
    else hi = mid;
  }
  const a = frames[Math.max(0, lo - 1)];
  const b = frames[lo];
  return Math.abs(a.t - t) <= Math.abs(b.t - t) ? a : b;
}

export function maskCenter(m: Mask): { x: number; y: number } {
  return { x: (m.left + m.right) / 2, y: (m.top + m.bottom) / 2 };
}
