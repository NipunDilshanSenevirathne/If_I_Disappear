import type { Lang, Schedule } from './types';
import { format as fill } from '../i18n';
import type { Dict } from '../i18n/en';

const LOCALE: Record<Lang, string> = { en: 'en-GB', si: 'si-LK' };

function parseDate(iso: string): Date {
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number);
  return new Date(Date.UTC(y, (m || 1) - 1, d || 1, 12));
}

export function longDate(iso: string | null | undefined, lang: Lang): string {
  if (!iso) return '';
  try {
    return new Intl.DateTimeFormat(LOCALE[lang], { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' }).format(parseDate(iso));
  } catch {
    return iso.slice(0, 10);
  }
}

export function shortDate(iso: string | null | undefined, lang: Lang): string {
  if (!iso) return '';
  try {
    return new Intl.DateTimeFormat(LOCALE[lang], { day: 'numeric', month: 'short', timeZone: 'UTC' }).format(parseDate(iso));
  } catch {
    return iso.slice(5, 10);
  }
}

export function weekday(iso: string, lang: Lang): string {
  try {
    return new Intl.DateTimeFormat(LOCALE[lang], { weekday: 'long', timeZone: 'UTC' }).format(parseDate(iso));
  } catch {
    return '';
  }
}

export function dateTime(iso: string, lang: Lang): string {
  try {
    return new Intl.DateTimeFormat(LOCALE[lang], { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Colombo' }).format(new Date(iso));
  } catch {
    return iso;
  }
}

export function daysBetween(a: string, b: string): number {
  return Math.round((parseDate(b).getTime() - parseDate(a).getTime()) / 86_400_000);
}

/** "06:00" -> "6 a.m." / "උදේ 6" */
export function clock(time: string | null | undefined, lang: Lang): string {
  if (!time) return '';
  const [hh, mm] = time.split(':').map(Number);
  if (Number.isNaN(hh)) return time;
  const minutes = mm ? `:${String(mm).padStart(2, '0')}` : '';
  if (lang === 'si') {
    const part = hh < 12 ? 'උදේ' : hh < 15 ? 'දවල්' : hh < 19 ? 'හවස' : 'රෑ';
    const h12 = hh % 12 === 0 ? 12 : hh % 12;
    return `${part} ${h12}${minutes}`;
  }
  const h12 = hh % 12 === 0 ? 12 : hh % 12;
  return `${h12}${minutes} ${hh < 12 ? 'a.m.' : 'p.m.'}`;
}

function ordinal(n: number): string {
  const s = ['th', 'st', 'nd', 'rd'];
  const v = n % 100;
  return `${n}${s[(v - 20) % 10] || s[v] || s[0]}`;
}

export function scheduleText(s: Schedule | null | undefined, d: Dict, lang: Lang): string {
  if (!s) return '';
  let base: string;
  switch (s.freq) {
    case 'daily':
      base = d.task.daily;
      break;
    case 'weekly':
      base = fill(d.task.weekly, { day: s.weekday != null ? d.days[s.weekday] : '' });
      break;
    case 'monthly':
      base = fill(d.task.monthly, { day: s.day_of_month != null ? (lang === 'en' ? ordinal(s.day_of_month) : String(s.day_of_month)) : '' });
      break;
    case 'once':
      base = d.task.once;
      break;
    default:
      base = d.task.when_needed;
  }
  const parts = [base];
  if (s.time) parts.push(fill(d.task.at, { time: clock(s.time, lang) }));
  if (s.duration_min) parts.push(fill(d.task.for, { n: s.duration_min }));
  return parts.join(' ');
}

export function seconds(t: number): string {
  const m = Math.floor(t / 60);
  const s = Math.floor(t % 60);
  return `${m}:${String(s).padStart(2, '0')}`;
}

export function usd(n: number): string {
  return `US$${n.toFixed(n < 0.01 && n > 0 ? 4 : 2)}`;
}

export function number(n: number, lang: Lang): string {
  return new Intl.NumberFormat(LOCALE[lang]).format(n);
}
