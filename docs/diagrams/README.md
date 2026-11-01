# Diagrams

Every part of If I Disappear, drawn. Each diagram is here as a PNG (for reading) and an SVG (to scale), and every number on them comes from a real run: the live check on Meta's Model API (`evals/results/live_check.json`), the evaluation ([EVALUATION.md](../EVALUATION.md)) and the Sinhala speech measurement.

**Colours mean the same thing on every diagram:**

| Colour | Means |
|---|---|
| Amber | a person: the owner, the people staying, anyone holding a sticker |
| Blue outline | a Meta model on the Meta Model API: Muse Spark 1.3, Muse Wonder 1.0, SAM 3.1, Muse Voice Transcribe, Muse Image |
| Teal outline | Meta's open weights: Omnilingual ASR (self-hosted), Muse Spark Open (Fireworks AI) |
| Navy | code that decides: the witnesses, the pinned rules, the fence, the engine |
| Grey | what is kept on disk: the hash-chained log, the results |
| Purple | privacy |
| Green, yellow, red | verified, needs review, refused |

| # | Diagram | What it shows |
|---|---|---|
| 01 | [The whole system](#01-the-whole-system) | People, the web app, the server's parts, and the Meta models behind them |
| 02 | [A walk-through, step by step](#02-a-walk-through-step-by-step) | Convert, hear, privacy, read, check, decide, with the live check's timings |
| 03 | [Three witnesses](#03-three-witnesses) | How one fact is checked by code, SAM 3.1 and Muse Wonder before the owner sees it |
| 04 | [Prove it](#04-prove-it-show-me-and-tell-me) | Show me (a photo) and tell me (an explanation), and what code requires of each |
| 05 | [The help line](#05-the-help-line-and-its-fence) | Emergencies first, then Muse Spark's tool loop inside a fence |
| 06 | [Privacy](#06-privacy) | Secrets hidden in the words and the sound, cards blurred, medicine refused |
| 07 | [The log](#07-the-hash-chained-log) | The hash-chained, append-only log and the pure projection that reads it |
| 08 | [The engine](#08-the-engine) | Jobs, coverage, the absence day by day, the teaching plan, the forgotten questions |
| 09 | [Who can open what](#09-who-can-open-what) | Signed, scoped links: the owner, each person, each sticker |
| 10 | [Meta's models together](#10-metas-seven-models-and-how-they-check-each-other) | Seven Meta models, each doing what it does best, and how they check each other |
| 11 | [Deployment](#11-deployment) | Two Hugging Face Spaces, and the alternatives |
| 12 | [One live walk-through](#12-one-live-walk-through-as-it-happened) | The third live check on Meta's API, call by call |
| 13 | [The evaluation loop](#13-the-evaluation-loop) | What was measured, and how each finding changed the code |
| 14 | [Sinhala speech](#14-sinhala-speech) | Omnilingual ASR, self-hosted, and the two guards around it |
| 15 | [A family's journey](#15-a-familys-journey) | Before she leaves, the day she leaves, the two years away |
| | [Charts](#charts) | The evaluation, the code checks, Sinhala speech, the live check's cost |

To redraw them: `python scripts/render_diagrams.py` (the Mermaid ones, from `src/`) and `python scripts/make_figures.py` (01, 10 and the charts, from the result files).

## 01. The whole system

![The system: people at the top, the web app, the server's parts in navy, and the Meta models below](01-system-overview.png)

## 02. A walk-through, step by step

The timings are from the last live run through the web app (1 November): a 71-second English walk-through of six rooms, 158 seconds from upload to 18 checked facts.

![The walk-through pipeline: convert, hear, privacy, read, check, decide, each with its time](02-walkthrough-pipeline.png)

## 03. Three witnesses

![One fact from Muse Spark checked by the words, the pixels and a second reading, then the pinned rules](03-three-witnesses.png)

## 04. Prove it: show me and tell me

![Show me: SAM 3.1 finds the object, Muse Spark compares; tell me: Muse Spark checks each point, code checks the quotes](04-prove-it.png)

## 05. The help line, and its fence

![A question: emergencies are decided by code first; then Muse Spark's tool loop, and code refuses any job the search didn't return](05-help-agent.png)

## 06. Privacy

![Secrets hidden in the words and silenced in the sound; SAM 3.1 finds cards and screens for code to blur; medicine refused](06-privacy.png)

## 07. The hash-chained log

![Every event names who wrote it, is chained to the one before, and is read by a pure function](07-ledger.png)

## 08. The engine

![Accepted facts and proofs become jobs and coverage, then the board, the simulation, the teaching plan and the questions](08-engine.png)

## 09. Who can open what

![Three kinds of signed link: the owner's, each person's, and each sticker's, all revoked by one rotation](09-access.png)

## 10. Meta's seven models, and how they check each other

![Muse Wonder, Muse Spark and SAM 3.1 at the top with the checks between them; four more models below](10-meta-models.png)

## 11. Deployment

![Two Hugging Face Spaces: the app and Sinhala speech, with the Meta Model API and WhatsApp beside them](11-deployment.png)

## 12. One live walk-through, as it happened

The live check on 1 November 2026, on the final code: 37 model calls, $0.34, 114 events in the log, the chain intact.

![A sequence diagram of the live check, from the upload to the tracking of three objects](12-live-walkthrough.png)

## 13. The evaluation loop

![Evaluation sets, the live check and Sinhala voices feed the results; what they taught changed the code; tests re-run after every change](13-evaluation-loop.png)

## 14. Sinhala speech

![Sinhala speech: cut at pauses, Omnilingual ASR, the joiner put back, and anything not in Sinhala letters marked unclear](14-sinhala-speech.png)

## 15. A family's journey

![Before she leaves: walk, review, prove, the board. The day she leaves: the card, the stickers, the offline pack. Away: the help line, emergencies, proofs that run out](15-family-journey.png)

## Charts

![Seven Meta models, three witnesses, $0.34 a live walk-through, 12.4% Sinhala character error rate, 371 automated checks](charts/at-a-glance.png)

![The model suites on Muse Spark 1.3 and Muse Spark Open, side by side](charts/model-suites.png)

![The code checks: 81 of 81 misquotes caught, 16 of 16 secrets hidden, 12 of 12 medical instructions refused, 8 of 8 mixed alphabets sent to review](charts/code-checks.png)

![Sinhala character error rates for the two CTC models, on all clips and on the clips heard in Sinhala letters](charts/sinhala-speech.png)

![What one live walk-through cost, by purpose](charts/live-check-cost.png)
