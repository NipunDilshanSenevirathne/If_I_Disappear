import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { en, type Dict } from './en';
import { si } from './si';

export type Lang = 'en' | 'si';
const DICTS: Record<Lang, Dict> = { en, si };
const KEY = 'iid.lang';

function initial(): Lang {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved === 'en' || saved === 'si') return saved;
  } catch {
    /* storage may be blocked */
  }
  return typeof navigator !== 'undefined' && navigator.language?.toLowerCase().startsWith('si') ? 'si' : 'en';
}

type Ctx = { lang: Lang; setLang: (l: Lang) => void; d: Dict; t: (path: string, vars?: Record<string, string | number>) => string };
const I18n = createContext<Ctx | null>(null);

function lookup(d: Dict, path: string): unknown {
  return path.split('.').reduce<unknown>((node, key) => (node && typeof node === 'object' ? (node as Record<string, unknown>)[key] : undefined), d);
}

export function format(template: string, vars?: Record<string, string | number>): string {
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (_, k) => (vars[k] !== undefined ? String(vars[k]) : `{${k}}`));
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(initial);
  const setLang = useCallback((l: Lang) => {
    setLangState(l);
    try {
      localStorage.setItem(KEY, l);
    } catch {
      /* ignore */
    }
  }, []);
  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);
  const value = useMemo<Ctx>(() => {
    const d = DICTS[lang];
    return {
      lang,
      setLang,
      d,
      t: (path, vars) => {
        const hit = lookup(d, path) ?? lookup(en, path);
        return typeof hit === 'string' ? format(hit, vars) : path;
      },
    };
  }, [lang, setLang]);
  return <I18n.Provider value={value}>{children}</I18n.Provider>;
}

export function useI18n(): Ctx {
  const ctx = useContext(I18n);
  if (!ctx) throw new Error('I18nProvider missing');
  return ctx;
}

/** Pick the Sinhala field when Sinhala is on and the field exists, else English. */
export function pick(obj: object | null | undefined, field: string, lang: Lang): string {
  if (!obj) return '';
  const rec = obj as Record<string, unknown>;
  const si = rec[`${field}_si`];
  const enV = rec[`${field}_en`];
  if (lang === 'si' && typeof si === 'string' && si.trim()) return si;
  return typeof enV === 'string' ? enV : '';
}
