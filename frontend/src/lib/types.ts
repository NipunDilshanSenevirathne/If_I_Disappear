export type Lang = 'en' | 'si';
export type Coverage = 'covered' | 'at_risk' | 'uncovered' | 'unknown';
export type Safety = 'none' | 'electricity' | 'gas' | 'water' | 'fire';
export type Role = 'leaving' | 'staying' | 'helper';

export interface Person {
  id: string;
  name: string;
  role: Role;
  language: Lang;
  relation: string;
  whatsapp: string | null;
}

export interface Household {
  id: string;
  name: string;
  created_at: string;
  absence: { start: string; end: string } | null;
  default_language: Lang;
  sample: boolean;
}

export interface Mask {
  path: string;
  left: number;
  top: number;
  right: number;
  bottom: number;
  width: number;
  height: number;
  confidence?: number | null;
  object_id?: string | null;
}

export interface Schedule {
  freq: 'daily' | 'weekly' | 'monthly' | 'when_needed' | 'once';
  weekday: number | null;
  day_of_month: number | null;
  time: string | null;
  duration_min: number | null;
}

export interface Bilingual {
  text_en: string;
  text_si: string;
}

export interface TaskPerson {
  person_id: string;
  name: string;
  show: boolean | null;
  tell: boolean | null;
  proven: boolean;
  proven_until: string | null;
  /** Passed before the job changed, so it needs proving again. */
  stale?: ('show' | 'tell')[];
}

export interface TaskCard {
  key: string;
  type: string;
  title_en: string;
  title_si: string;
  safety: Safety;
  coverage: Coverage;
  people: TaskPerson[];
  steps: (Bilingual & { id: string; quote: string; time: number; recording_id: string })[];
  warnings: (Bilingual & { id: string; quote: string; time: number; recording_id: string })[];
  contacts: (Bilingual & { id: string; name: string; role: string; quote: string; time: number; recording_id: string })[];
  facts: (Bilingual & { id: string; kind: string; quote: string; time: number; recording_id: string })[];
  schedule: Schedule | null;
  object: { noun: string; recording_id: string; keyframe_id: string | null; keyframe_path: string | null; time: number; mask: Mask | null; claim_id: string } | null;
  clip: { recording_id: string; start: number; end: number } | null;
  lesson_minutes: number;
  next: string | null;
  gaps: number;
  notes: { slot: string; text: string }[];
  points: (Bilingual & { point_id: string; safety: boolean })[];
}

export interface Gap {
  task_key: string;
  slot: string;
  question_en: string;
  question_si: string;
  safety: Safety;
}

export interface Board {
  household: Household;
  today: string;
  leaving: Person | null;
  people: Person[];
  headline: { stop_tomorrow: number; total: number; task_keys: string[] };
  counts: Record<Coverage, number>;
  review: { verified: number; needs_review: number; blocked: number; left_out: number };
  tasks: TaskCard[];
  simulation: {
    start: string;
    end: string;
    days: number;
    /** The end of the absence; the simulation stops at `end`, five years at most. */
    asked_end?: string;
    capped?: boolean;
    first_stop: { date: string; task_key: string } | null;
    tasks: { task_key: string; first_stop: string | null; next: string | null; occurrences: number; stops: number }[];
    weeks: { week_start: string; covered: number; at_risk: number; uncovered: number; unknown: number }[];
  };
  plan: {
    days: { date: string; minutes: number; sessions: { minutes: number; person_id: string; task_key: string; value: number; why: string }[] }[];
    days_available: number;
    minutes_per_day: number;
    unscheduled: { person_id: string; task_key: string; minutes: number }[];
  };
  gaps: Gap[];
  costs_usd: number;
  ledger: { events: number; head: string };
  sample: boolean;
  sample_sources?: { reading: string; outlines: string };
  mode: 'sample' | 'live' | 'judge';
  you: { role: 'owner' | 'person' | 'sticker'; person_id: string | null };
}

export interface Witness {
  name: 'words' | 'pixels' | 'reading';
  status: 'pass' | 'fail' | 'disagree' | 'skipped' | 'not_run';
  detail: string;
  evidence: Record<string, unknown>;
}

export type ClaimStatus = 'proposed' | 'verified' | 'needs_review' | 'blocked' | 'accepted' | 'rejected';

export interface Claim {
  id: string;
  recording_id: string;
  kind: string;
  task_key: string;
  task_type: string;
  title_en: string;
  title_si: string;
  text_en: string;
  text_si: string;
  object_noun: string;
  quote: string;
  turn_id: string;
  time: number;
  point: [number, number] | null;
  keyframe_id: string | null;
  safety: Safety;
  schedule: Schedule | null;
  contact: { name: string; role: string; phone_hint: string } | null;
  witnesses: Witness[];
  status: ClaimStatus;
  mask: Mask | null;
  blocked_reason: string;
  /** Languages the owner rewrote: the witnesses checked the earlier wording. */
  edited?: Lang[];
  /** Languages showing the owner's new words until they are translated too. */
  untranslated?: Lang[];
}

/** A sentence the owner said that no fact came from. `reason` is decided by code. */
export interface LeftOut {
  recording_id: string;
  turn_id: string;
  start: number;
  end: number;
  text: string;
  lang: Lang;
  reason: 'medical' | 'unused' | 'unclear';
}

export interface Keyframe {
  id: string;
  time: number;
  path: string;
  width: number;
  height: number;
}

export interface Turn {
  id: string;
  start: number;
  end: number;
  text: string;
  lang: Lang;
  speaker: string | null;
}

export interface ClipFrame extends Mask {
  t: number;
}

export interface Clip {
  claim_id: string;
  recording_id: string;
  start: number;
  end: number;
  frames: ClipFrame[];
  sam_text: string | null;
  clip?: string | null;
}

export interface Recording {
  id: string;
  kind: string;
  lang: Lang;
  video: string | null;
  audio: string | null;
  duration: number;
  width: number;
  height: number;
  keyframes: Keyframe[];
  turns: Turn[];
  scrubbed: { kind: string; count?: number }[];
  redactions: unknown[];
  clips: Clip[];
  /** A recording as one job shows it: `video` is that job's own clip, starting `video_start`
      seconds into the walk-through. */
  scoped?: boolean;
  /** The same job clip as WebM, for browsers that can't play H.264. */
  video_webm?: string | null;
  video_start?: number;
  poster?: string | null;
  task_key?: string;
}

export interface ProofResult {
  passed: boolean;
  /** For a photo: verified, a different one (mismatch), or couldn't tell (cannot_verify). */
  outcome?: 'verified' | 'mismatch' | 'cannot_verify';
  reasons_en: string[];
  reasons_si: string[];
  evidence: Record<string, unknown> & {
    photo?: string;
    mask?: Mask | null;
    confidence?: number;
    found?: number;
    matched?: string[];
    mismatches?: string[];
    explanation_en?: string;
    explanation_si?: string;
    transcript?: string;
    lang?: Lang;
    points?: { point_id: string; covered: boolean; verified?: boolean; safety?: boolean; quote: string; text_en?: string; text_si?: string }[];
    coverage?: number;
  };
  proof_id: string;
}

export interface HelpResult {
  id: string;
  task_key: string | null;
  decided_by: string;
  reason: string;
  reason_si?: string;
  emergency?: boolean;
  /** A question about medicine: answered by code, with who can help. */
  medical?: boolean;
  candidates?: { task_key: string; score: number }[];
  task?: TaskCard | null;
  contacts: { name: string; role: string; for: string; for_si: string }[];
  question?: string;
}

export interface LedgerEvent {
  seq: number;
  at: string;
  type: string;
  actor: string;
  payload: Record<string, unknown>;
  digest: string;
  prev: string;
}

export interface Health {
  ok: boolean;
  version: string;
  mode: 'live' | 'judge';
  models: Record<string, string | null>;
  sinhala_speech: boolean;
  whatsapp: boolean;
  public_live: boolean;
  /** A live server where a new real home needs the invite code. */
  invite_only?: boolean;
  max_upload_mb?: number;
  policy_sha256: string;
}
