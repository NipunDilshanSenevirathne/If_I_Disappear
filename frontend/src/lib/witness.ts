import type { Lang } from './types';

/**
 * The checks write their findings in English (that is what the log stores). The app
 * shows them in Sinhala too: known sentences are translated here, anything else is
 * shown as written.
 */
const EXACT: Record<string, string> = {
  'Found word for word in what was said, at the right moment.': 'ඔබ කියපු දේ ඇතුළේ, හරි මොහොතේම, වචනයෙන් වචනය හම්බ වුණා.',
  'These exact words are not in what was said.': 'මේ වචනම ඔබ කියපු දේ ඇතුළේ නැහැ.',
  'The words are real, but they were said at a different moment from the one shown.': 'වචන ඇත්ත, ඒත් ඒවා කිව්වේ පෙන්නපු මොහොතේ නෙවෙයි, වෙනත් වෙලාවක.',
  'The quote is too short to check.': 'පරීක්ෂා කරන්න මේ උපුටා දැක්වීම කෙටි වැඩියි.',
  'The claim cites a turn that does not exist.': 'මේ කරුණ පෙන්වන්නේ නැති කතා කොටසක්.',
  "Muse Spark's point is inside SAM 3.1's mask.": 'Muse Spark ඇඟිල්ල දිගු කළ තැන SAM 3.1 ඇඳපු ඉර ඇතුළේ.',
  'No physical object to find.': 'හොයන්න භෞතික දෙයක් නැහැ.',
  'No video frame at that moment.': 'ඒ මොහොතේ වීඩියෝ රාමුවක් නැහැ.',
  'Segmentation did not run.': 'SAM 3.1 දුවලා නැහැ.',
  'The second reading did not run.': 'දෙවන කියවීම දුවලා නැහැ.',
  'A second model read the same evidence and agrees.': 'දෙවන මොඩලයක් එකම සාක්ෂි කියවලා එකඟ වෙනවා.',
  'A second model is not sure this is right.': 'මේක හරිද කියලා දෙවන මොඩලයට විශ්වාස නැහැ.',
  'The second reading gave no clear verdict.': 'දෙවන කියවීමෙන් පැහැදිලි තීරණයක් ආවේ නැහැ.',
  "The owner's words and the frame both support this exactly as written.": 'අයිතිකරුගේ වචන සහ රාමුව දෙකම මේක ලියලා තියෙන විදිහටම සනාථ කරනවා.',
  'The Sinhala text mixes in letters from another script.': 'සිංහල පාඨයේ වෙනත් භාෂාවක අකුරු මිශ්‍ර වෙලා.',
  "The Sinhala text has a character that isn't a Sinhala letter.": 'සිංහල පාඨයේ සිංහල අකුරක් නොවන ලකුණක් තියෙනවා.',
  'not checked': 'පරීක්ෂා කළේ නැහැ',
  "If I Disappear doesn't store medical instructions. Please keep those on paper from the doctor or pharmacy.":
    'If I Disappear වෛද්‍ය උපදෙස් ගබඩා කරන්නේ නැහැ. ඒවා වෛද්‍යවරයාගෙන් හෝ ෆාමසියෙන් ලැබුණු කඩදාසියක තියාගන්න.',
};

const PATTERNS: [RegExp, (m: RegExpMatchArray) => string][] = [
  [/^SAM 3\.1 found no “(.+)” in this frame\.$/, (m) => `මේ රාමුවේ SAM 3.1 ට “${m[1]}” හම්බ වුණේ නැහැ.`],
  [/^SAM 3\.1 found (\d+) possible “(.+)” and nothing says which one\.$/, (m) => `SAM 3.1 ට “${m[2]}” ${m[1]} ක් හම්බ වුණා, ඒත් ඒ අතරින් මොකක්ද කියලා කියන්න දෙයක් නැහැ.`],
  [/^The models agree on the spot, but SAM 3\.1 is only (\d+)% sure it is a “(.+)”\.$/, (m) => `මොඩල් දෙකම එකම තැනට එකඟයි, ඒත් ඒක “${m[2]}” කියලා SAM 3.1 ට ${m[1]}% ක් විතරයි විශ්වාස.`],
  [/^Muse Spark pointed somewhere else from the “(.+)” SAM 3\.1 found\.$/, (m) => `SAM 3.1 හොයාගත්ත “${m[1]}” නෙවෙයි, Muse Spark ඇඟිල්ල දිගු කළේ වෙන තැනකට.`],
];

export function translateFinding(text: string, lang: Lang): string {
  if (lang !== 'si' || !text) return text;
  if (EXACT[text]) return EXACT[text];
  for (const [re, fn] of PATTERNS) {
    const m = text.match(re);
    if (m) return fn(m);
  }
  return text;
}

const MODEL_NAMES: Record<string, string> = {
  'muse-spark-1.3': 'Muse Spark 1.3',
  'muse-spark-open': 'Muse Spark Open',
  'accounts/fireworks/models/muse-spark-open': 'Muse Spark Open',
  'muse-wonder-1.0': 'Muse Wonder',
  'sam-3.1': 'SAM 3.1',
  'muse-voice-transcribe-1.0': 'Muse Voice Transcribe',
  'omnilingual-asr': 'Omnilingual ASR',
};

/** A model id as people say it: "muse-spark-open" -> "Muse Spark Open". */
export function modelName(id: string): string {
  const bare = id.replace(/^(model|sample|recorded|replay):/, '');
  return bare
    .split('+')
    .map((part) => MODEL_NAMES[part.trim()] || MODEL_NAMES[part.trim().split('/').pop() || ''] || part.trim())
    .join(' + ');
}

/** A rule's reason, "words: These exact words are not in what was said.; pixels: …", as readable lines. */
export function gateReasons(reason: string, lang: Lang, label: (name: string) => string): string[] {
  return reason
    .split(/;\s+(?=[a-z_]+:)/)
    .filter(Boolean)
    .map((part) => {
      const m = part.match(/^([a-z_]+):\s*(.*)$/);
      if (!m) return translateFinding(part, lang);
      return `${label(m[1])}: ${translateFinding(m[2], lang)}`;
    });
}

/** Who wrote a log entry, in plain words. */
export function actorKind(actor: string): 'model' | 'recorded' | 'sample' | 'code' | 'person' | 'system' {
  if (actor.startsWith('recorded:') || actor.startsWith('replay:')) return 'recorded';
  if (actor.startsWith('sample:')) return 'sample';
  if (actor.startsWith('model:')) return 'model';
  if (actor === 'code') return 'code';
  if (actor === 'system') return 'system';
  return 'person';
}
