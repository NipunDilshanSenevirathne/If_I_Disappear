import { BookOpenCheck, CircleAlert, CircleCheck, CircleHelp, CircleX, Clock3, Droplets, Flame, Minus, Quote, ScanEye, TriangleAlert, Zap } from 'lucide-react';
import { useI18n } from '../i18n';
import type { Coverage, Safety, Witness } from '../lib/types';
import { translateFinding } from '../lib/witness';

const COVERAGE_ICON = { covered: CircleCheck, at_risk: Clock3, uncovered: CircleAlert, unknown: CircleHelp };
const COVERAGE_CLASS = { covered: 'chip-ok', at_risk: 'chip-risk', uncovered: 'chip-bad', unknown: 'chip-unknown' };

export function CoverageChip({ coverage, compact = false }: { coverage: Coverage; compact?: boolean }) {
  const { d } = useI18n();
  const Icon = COVERAGE_ICON[coverage];
  return (
    <span className={`chip ${COVERAGE_CLASS[coverage]}`}>
      <Icon aria-hidden />
      <span className={compact ? 'visually-hidden' : undefined}>{d.status[coverage]}</span>
    </span>
  );
}

const SAFETY_ICON = { electricity: Zap, gas: Flame, fire: Flame, water: Droplets, none: null };

export function SafetyTag({ safety }: { safety: Safety }) {
  const { d } = useI18n();
  const Icon = SAFETY_ICON[safety];
  if (!Icon) return null;
  return (
    <span className={`chip chip-safety chip-safety-${safety}`}>
      <Icon aria-hidden />
      {d.safety[safety]}
    </span>
  );
}

const WITNESS_ICON = { words: Quote, pixels: ScanEye, reading: BookOpenCheck };
const WITNESS_STATUS_ICON = { pass: CircleCheck, fail: CircleX, disagree: TriangleAlert, skipped: Minus, not_run: Minus };
const WITNESS_STATUS_CLASS = { pass: 'chip-ok', fail: 'chip-bad', disagree: 'chip-risk', skipped: 'chip-unknown', not_run: 'chip-unknown' };

export function WitnessList({ witnesses, required }: { witnesses: Witness[]; required?: ('words' | 'pixels' | 'reading')[] }) {
  const { d, lang } = useI18n();
  const names = required && required.length ? required : (['words', 'pixels', 'reading'] as const).filter((n) => witnesses.some((w) => w.name === n));
  return (
    <ul className="witness-list">
      {names.map((name) => {
        const w = witnesses.find((x) => x.name === name);
        const status = w?.status ?? 'not_run';
        const Icon = WITNESS_ICON[name];
        const StatusIcon = WITNESS_STATUS_ICON[status];
        return (
          <li key={name} className={`witness witness-${status}`}>
            <span className="witness-icon" aria-hidden>
              <Icon />
            </span>
            <span className="witness-body">
              <span className="witness-head">
                <strong>{d.witness[name]}</strong>
                <span className={`chip ${WITNESS_STATUS_CLASS[status]}`}>
                  <StatusIcon aria-hidden />
                  {d.witness[status]}
                </span>
              </span>
              {w?.detail && <span className="witness-detail">{lang === 'si' && typeof w.evidence?.detail_si === 'string' && w.evidence.detail_si ? (w.evidence.detail_si as string) : translateFinding(w.detail, lang)}</span>}
            </span>
          </li>
        );
      })}
    </ul>
  );
}
