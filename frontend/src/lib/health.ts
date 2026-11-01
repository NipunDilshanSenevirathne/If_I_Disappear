import { useEffect, useState } from 'react';
import { Api } from './api';
import type { Health } from './types';

let cached: Health | null = null;
let pending: Promise<Health> | null = null;

export function loadHealth(): Promise<Health> {
  if (cached) return Promise.resolve(cached);
  pending ??= Api.health().then((h) => (cached = h));
  return pending;
}

export function useHealth(): Health | null {
  const [h, setH] = useState<Health | null>(cached);
  useEffect(() => {
    let live = true;
    loadHealth()
      .then((x) => live && setH(x))
      .catch(() => {
        pending = null;
      });
    return () => {
      live = false;
    };
  }, []);
  return h;
}
