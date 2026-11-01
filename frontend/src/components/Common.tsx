import { CircleAlert, Phone, WifiOff } from 'lucide-react';
import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from 'react';
import { useI18n } from '../i18n';
import { ApiError } from '../lib/api';

export function Loading({ label }: { label?: string }) {
  const { d } = useI18n();
  return (
    <div className="state state-loading" role="status">
      <span className="spinner" aria-hidden />
      <span>{label || d.common.loading}</span>
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: Error; onRetry?: () => void }) {
  const { d } = useI18n();
  const offline = error instanceof ApiError && error.code === 'offline';
  return (
    <div className="state state-error" role="alert">
      {offline ? <WifiOff aria-hidden /> : <CircleAlert aria-hidden />}
      <p>{offline ? d.common.offlineError : messageOf(error, d.common.error, d.errors)}</p>
      {onRetry && (
        <button type="button" className="btn" onClick={onRetry}>
          {d.common.retry}
        </button>
      )}
    </div>
  );
}

/** What to tell the person about an error. With `codes` (the dictionary's `errors`), a code the
    server sent (budget, model_timeout, copied…) is said in the reader's language. */
export function messageOf(error: unknown, fallback: string, codes?: Record<string, string>): string {
  if (error instanceof ApiError) {
    if (codes && error.code && codes[error.code]) return codes[error.code];
    if (codes && error.status === 0 && codes.offline) return codes.offline;
    return error.message && error.message !== 'offline' ? error.message : fallback;
  }
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}

export function EmptyState({ text, children }: { text: string; children?: ReactNode }) {
  return (
    <div className="state state-empty">
      <p>{text}</p>
      {children}
    </div>
  );
}

export const EMERGENCY = [
  { key: 'fire', number: '110' },
  { key: 'ambulance', number: '1990' },
  { key: 'police', number: '119' },
] as const;

export function EmergencyNumbers({ compact = false }: { compact?: boolean }) {
  const { d } = useI18n();
  return (
    <ul className={`emergency${compact ? ' emergency-compact' : ''}`} aria-label={d.help.numbersLabel}>
      {EMERGENCY.map((e) => (
        <li key={e.key}>
          <a href={`tel:${e.number}`} className="emergency-call">
            <Phone aria-hidden />
            <span className="emergency-name">{d.help.service[e.key]}</span>
            <span className="emergency-number">{e.number}</span>
          </a>
        </li>
      ))}
    </ul>
  );
}

export function Section({ title, action, children, id, className = '' }: { title?: ReactNode; action?: ReactNode; children: ReactNode; id?: string; className?: string }) {
  return (
    <section className={`section ${className}`} id={id} aria-labelledby={id && title ? `${id}-title` : undefined}>
      {(title || action) && (
        <div className="section-head">
          {title && <h2 id={id ? `${id}-title` : undefined}>{title}</h2>}
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

type Toast = { id: number; text: string; tone: 'ok' | 'bad' | 'info' };
const ToastCtx = createContext<(text: string, tone?: Toast['tone']) => void>(() => {});

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const next = useRef(1);
  const push = useCallback((text: string, tone: Toast['tone'] = 'info') => {
    const id = next.current++;
    setToasts((all) => [...all, { id, text, tone }]);
    window.setTimeout(() => setToasts((all) => all.filter((x) => x.id !== id)), 4200);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {toasts.map((x) => (
          <div key={x.id} className={`toast toast-${x.tone}`}>
            {x.text}
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

export function useToast() {
  return useContext(ToastCtx);
}
