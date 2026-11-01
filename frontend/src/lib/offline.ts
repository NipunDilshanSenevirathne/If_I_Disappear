import { Api, getToken, mediaUrl } from './api';
import { canPlay } from './media';
import type { Board } from './types';

const CACHE = 'iid-offline-v1';

export function offlineSupported(): boolean {
  return typeof caches !== 'undefined' && 'serviceWorker' in navigator;
}

export function registerServiceWorker(): void {
  if (!('serviceWorker' in navigator) || location.hostname === 'localhost' && location.port === '5173') return;
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {
      /* offline support is a bonus, never a blocker */
    });
  });
}

export type OfflineSave = { saved: number; total: number; failed: number };

/** Save everything a family member needs to follow the handover with no connection: the app,
    the board, and each job's own view, clip and still. Says how much really saved: a pack with a
    piece missing is not reported as complete. */
export async function saveOffline(householdId: string, board: Board, onProgress?: (done: number, total: number) => void): Promise<OfflineSave> {
  const cache = await caches.open(CACHE);
  const token = getToken(householdId);
  const urls = new Set<string>(['/', '/index.html', '/manifest.webmanifest', '/icons/icon.svg', `/h/${householdId}`]);
  for (const entry of performance.getEntriesByType('resource') as PerformanceResourceTiming[]) {
    const u = new URL(entry.name);
    if (u.origin === location.origin && (u.pathname.startsWith('/assets/') || u.pathname.startsWith('/icons/'))) urls.add(u.pathname);
  }
  urls.add(`/api/h/${householdId}/board?minutes=20`);
  let missing = 0;
  for (const task of board.tasks) {
    const rid = task.clip?.recording_id ?? task.object?.recording_id;
    if (task.object?.keyframe_path) urls.add(mediaUrl(householdId, task.object.keyframe_path));
    if (!rid) continue;
    // The same address a sticker asks for, so a sticker scanned on this phone finds it.
    urls.add(`/api/h/${householdId}/recordings/${encodeURIComponent(rid)}?task=${encodeURIComponent(task.key)}`);
    try {
      const rec = await Api.recording(householdId, rid, undefined, task.key);
      // The format this browser plays, so the clip plays offline here too.
      const clip = !canPlay('mp4') && rec.video_webm && canPlay('webm') ? rec.video_webm : rec.video;
      if (clip) urls.add(mediaUrl(householdId, clip));
      if (rec.poster) urls.add(mediaUrl(householdId, rec.poster));
    } catch {
      missing += 1; // its clip can't be listed now: counted as not saved
    }
  }
  const all = [...urls];
  const total = all.length + missing;
  let saved = 0;
  let done = 0;
  for (const url of all) {
    try {
      const headers: Record<string, string> = {};
      if (url.startsWith('/api/') && token) headers.Authorization = `Bearer ${token}`;
      const res = await fetch(url, { headers, cache: 'reload' });
      if (res.ok) {
        await cache.put(url, res);
        saved += 1;
      }
    } catch {
      /* counted below */
    }
    done += 1;
    onProgress?.(done, all.length);
  }
  const result = { saved, total, failed: total - saved };
  try {
    localStorage.setItem(`iid.offline.${householdId}`, JSON.stringify({ at: new Date().toISOString(), ...result }));
  } catch {
    /* ignore */
  }
  return result;
}

/** Take this home off this phone: its saved pages, clips and photos. The server, and other
    phones, are not touched. */
export async function forgetOffline(householdId: string): Promise<void> {
  try {
    if (typeof caches !== 'undefined') {
      const cache = await caches.open(CACHE);
      for (const request of await cache.keys()) {
        const path = new URL(request.url).pathname;
        if (path.startsWith(`/api/h/${householdId}/`) || path === `/h/${householdId}`) await cache.delete(request);
      }
    }
  } catch {
    /* nothing saved, or storage blocked */
  }
  try {
    localStorage.removeItem(`iid.offline.${householdId}`);
  } catch {
    /* ignore */
  }
}

/** What a link says about itself: which home, which role, which job. Its signature is not
    checked here (only the server can), so this is used for one thing: finding what this phone
    already saved, when there is no connection to ask the server. */
export function peekLink(token: string): { household: string; role: string; task: string | null } | null {
  const payload = token.split('.')[0];
  if (!payload) return null; // a compressed payload starts with '.', and a link's never is
  try {
    const b64 = payload.replace(/-/g, '+').replace(/_/g, '/');
    const raw = JSON.parse(atob(b64 + '='.repeat((4 - (b64.length % 4)) % 4))) as { h?: unknown; r?: unknown; k?: unknown };
    if (typeof raw.h !== 'string' || typeof raw.r !== 'string') return null;
    return { household: raw.h, role: raw.r, task: typeof raw.k === 'string' ? raw.k : null };
  } catch {
    return null;
  }
}

/** A sticker's job from the offline pack saved on this phone. A power cut often takes the
    Wi-Fi with it, and the sticker on the switch box is the one someone scans then. */
export async function savedSticker(token: string): Promise<{ householdId: string; household: Board['household']; task: Board['tasks'][number] } | null> {
  const link = peekLink(token);
  if (!link || link.role !== 'sticker' || !link.task || typeof caches === 'undefined') return null;
  try {
    const hit = await caches.match(`/api/h/${link.household}/board?minutes=20`, { ignoreVary: true });
    if (!hit) return null;
    const board = (await hit.json()) as Board;
    const task = board.tasks.find((t) => t.key === link.task);
    return task ? { householdId: link.household, household: board.household, task } : null;
  } catch {
    return null;
  }
}

/** When this phone last saved this home, and whether everything saved. */
export function savedOffline(householdId: string): (OfflineSave & { at: string }) | null {
  try {
    const raw = localStorage.getItem(`iid.offline.${householdId}`);
    if (!raw) return null;
    if (!raw.startsWith('{')) return { at: raw, saved: 0, total: 0, failed: 0 }; // an older save: assume complete
    return JSON.parse(raw) as OfflineSave & { at: string };
  } catch {
    return null;
  }
}
