# Design

## Who it is for

Three people use this app, and they are not the same person:

- **The person leaving**, usually in the last busy weeks before a flight, recording on a phone.
- **The people staying**: a husband or wife, a grandmother who reads Sinhala and may not read English, a teenager who reads both. They use it in the moment something has gone wrong, often in the dark.
- **Anyone at the object**: a neighbour holding a phone up to a QR sticker on the switch box.

So the rules are: big readable type, one job per screen, Sinhala first-class, nothing that depends on colour alone, and everything still working with no signal.

## The idea behind the look

**Night and lamp.** The house after dark, when the power goes and someone lights the lamp. A deep blue-green night (`#10212A`) for the frame of the app and the landing hero, and a warm lamp amber (`#F7B547`) for the one thing that matters on a screen: the outline around the object, the button to press. Status uses the colours of the island: paddy green for covered, laterite red for uncovered, lamp amber for at risk, dusk grey for unknown, and every status always has a word and an icon too.

| Token | Light | Dark | Use |
|---|---|---|---|
| `--night` | `#10212A` | — | App bar, landing hero, video stage |
| `--lamp` | `#F7B547` | `#F7B547` | SAM outlines, primary actions, focus |
| `--ok` | `#23784A` | `#5CC28A` | Covered, passed |
| `--bad` | `#B0452B` | `#F08A6E` | Uncovered, failed, refused |
| `--risk` | `#8A5300` | `#F7B547` | At risk, needs review |
| `--unknown` | `#5B6470` | `#B5BDC7` | Not enough recorded |
| `--text` | `#13232B` | `#E8EFF1` | Body text |

All colours are tokens in `frontend/src/styles/tokens.css`, with a dark theme that follows the phone's setting or the switch in the menu. Text pairs meet WCAG AA contrast in both themes (checked by axe-core in the end-to-end tests).

## Type

- **Outfit** (variable) for English: geometric, open, friendly at large sizes, clear at small ones.
- **Yaldevi** (variable, by Mooniak) for Sinhala: designed for screens, with a generous x-height. Sinhala text is set with `lang="si"`, a slightly larger line height (1.75), and never with letter-spacing or all caps.
- Body text is 17 px with a 1.55 line height, because grandparents read this too. Anything you read is at least 15 px; only short labels (a status chip, a time) go smaller, down to 12 px.

Both fonts are self-hosted, so the app makes no third-party requests.

## Layout

Mobile first, designed at 375 px and checked at 1440 px with no sideways scrolling. The household app is a single column up to 760 px with a bottom navigation of five places (Home, Record, Prove, Help, Card), each with an icon and a label. Touch targets are at least 44 px.

The landing page follows a photographic hero with pinned objects: a real room at night, with the three objects the sample home pins (the switch box, the pump, the papers) marked where they are, the way the app marks them.

## The parts that carry the idea

- **The outline**: an amber SAM 3.1 mask over the still or the playing clip, with Muse Spark's point as a white dot. It is how the app says "this one, here".
- **The witnesses**: three rows on every fact (words, pixels, second reading), each with an icon, a status chip and a plain sentence, in both languages.
- **The quote**: the owner's own words, in the language they spoke, under the English, with the second they said it. Tapping plays from that second.
- **The board headline**: one sentence, "If Dilini left tomorrow, 4 of 6 jobs would stop or be at risk", because that is the question.

## Motion

Short and only where it explains something: the outline following the object in the clip, a check mark when a job turns green. Everything respects `prefers-reduced-motion`.

## Accessibility

- axe-core runs on every main screen in both languages in the end-to-end tests; no serious or critical issue is allowed.
- Every icon-only button has a label; focus is always visible; forms have visible labels.
- `html lang` switches with the language, so screen readers pronounce Sinhala as Sinhala.
- Status is never colour alone; outlines and points have legends.
- Video has the owner's words as captions, built from the facts and their times.

## Writing

Plain words, from the family's side: *Prove it*, *What do I do?*, *Not used*, *Waiting for you*. A button says what happens. Errors say what went wrong and what to do next. The Sinhala is natural spoken Sinhala, not a word-for-word translation of the English, and every string exists in both languages (`frontend/src/i18n/en.ts`, `si.ts`).
