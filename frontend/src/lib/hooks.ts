import { useCallback, useEffect, useRef, useState } from 'react';

export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]): { data: T | null; error: Error | null; loading: boolean; reload: () => void; setData: (d: T) => void } {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  const fnRef = useRef(fn);
  fnRef.current = fn;
  useEffect(() => {
    let live = true;
    setLoading(true);
    fnRef
      .current()
      .then((d) => {
        if (!live) return;
        setData(d);
        setError(null);
      })
      .catch((e: Error) => live && setError(e))
      .finally(() => live && setLoading(false));
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);
  const reload = useCallback(() => setTick((n) => n + 1), []);
  return { data, error, loading, reload, setData };
}

export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => typeof window !== 'undefined' && window.matchMedia(query).matches);
  useEffect(() => {
    const mq = window.matchMedia(query);
    const on = () => setMatches(mq.matches);
    mq.addEventListener('change', on);
    on();
    return () => mq.removeEventListener('change', on);
  }, [query]);
  return matches;
}

export function useReducedMotion(): boolean {
  return useMediaQuery('(prefers-reduced-motion: reduce)');
}

export function useOnline(): boolean {
  const [online, setOnline] = useState(() => (typeof navigator === 'undefined' ? true : navigator.onLine));
  useEffect(() => {
    const on = () => setOnline(navigator.onLine);
    window.addEventListener('online', on);
    window.addEventListener('offline', on);
    return () => {
      window.removeEventListener('online', on);
      window.removeEventListener('offline', on);
    };
  }, []);
  return online;
}

/** Record audio with the microphone. Returns a Blob when stopped. */
export function useRecorder() {
  const [state, setState] = useState<'idle' | 'recording' | 'denied'>('idle');
  const [seconds, setSeconds] = useState(0);
  const rec = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);
  const timer = useRef<number | null>(null);
  const resolver = useRef<((b: Blob | null) => void) | null>(null);

  const start = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mime = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg'].find((m) => MediaRecorder.isTypeSupported?.(m)) || '';
      const r = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
      chunks.current = [];
      r.ondataavailable = (e) => e.data.size && chunks.current.push(e.data);
      r.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunks.current, { type: r.mimeType || 'audio/webm' });
        resolver.current?.(blob);
        resolver.current = null;
      };
      r.start();
      rec.current = r;
      setSeconds(0);
      setState('recording');
      timer.current = window.setInterval(() => setSeconds((s) => s + 1), 1000);
    } catch {
      setState('denied');
    }
  }, []);

  const stop = useCallback(
    () =>
      new Promise<Blob | null>((resolve) => {
        if (timer.current) window.clearInterval(timer.current);
        if (!rec.current || rec.current.state === 'inactive') {
          setState('idle');
          resolve(null);
          return;
        }
        resolver.current = resolve;
        rec.current.stop();
        setState('idle');
      }),
    [],
  );

  useEffect(
    () => () => {
      if (timer.current) window.clearInterval(timer.current);
      if (rec.current && rec.current.state !== 'inactive') rec.current.stop();
    },
    [],
  );
  return { state, seconds, start, stop, supported: typeof window !== 'undefined' && 'MediaRecorder' in window && !!navigator.mediaDevices };
}
