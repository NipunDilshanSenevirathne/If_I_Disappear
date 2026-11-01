# Credits

## Photos

**The sample home's own photos** (the main switch box, a different switch box, the water pump and tank, the kitchen with the gas cylinder, and the bedroom cupboard with the white files) were made for this project with Meta's **Muse Image** (`muse-image-1.0`), by `scripts/make_sample_photos.py`. The prompts and response ids are kept in `backend/fixtures/base/photos.json`. Every outline drawn on them in the app is a real, recorded SAM 3.1 run.

The other photos are from [Unsplash](https://unsplash.com), used under the [Unsplash License](https://unsplash.com/license) (free to use, no permission needed):

| Where it appears | Photographer | Photo |
|---|---|---|
| Landing hero, and the sample home's bill scene: a lamp in a dark room | Arun Anoop | [photo-1524694344997-f872df30b642](https://images.unsplash.com/photo-1524694344997-f872df30b642) |
| Running water (the sample photo that is not the pump) | Gowtham AGM | [photo-1696371269814-ae41fc67cf03](https://images.unsplash.com/photo-1696371269814-ae41fc67cf03) |
| A warm room (landing page) | PhilCreates | [photo-1638035661684-f5d69e44d34f](https://images.unsplash.com/photo-1638035661684-f5d69e44d34f) |
| Lamp by the wall (power cut) | Khanh Do | [photo-1704536345279-4b7dfa0c166d](https://images.unsplash.com/photo-1704536345279-4b7dfa0c166d) |
| Train through the hills | Anton Lecock | [photo-1578517929167-db9ed31cd5c6](https://images.unsplash.com/photo-1578517929167-db9ed31cd5c6) |
| Nine Arches Bridge, Ella | Hendrik Cornelissen | [photo-1566296314736-6eaac1ca0cb9](https://images.unsplash.com/photo-1566296314736-6eaac1ca0cb9) |
| Phone with a QR code | Markus Winkler | [photo-1595079676339-1534801ad6cf](https://images.unsplash.com/photo-1595079676339-1534801ad6cf) |
| Cargo ship at sea | Kinsey Wang | [Unsplash page](https://unsplash.com/photos/a-large-cargo-ship-in-the-middle-of-the-ocean-bOGNLYidRXY) |

The same lists are shown in the app at `/credits`.

**The photo-check evaluation set** (`evals/data/show/`, used only by `evals/run_evals.py`, never shown in the app) is made of crops, turns and lighting changes of these Unsplash photos, under the same licence:

| Images | Photographer | Photo |
|---|---|---|
| The breaker row under a blue bar: `ref-breaker`, `breaker-same-angle`, `breaker-same-close`, `pump-vs-breaker` | mostafa mahmoudi | [photo-1635335874521-7987db781153](https://images.unsplash.com/photo-1635335874521-7987db781153) |
| Another switch panel: `breaker-other-panel` | Markus Spiske | [photo-1544724569-5f546fd6f2b5](https://images.unsplash.com/photo-1544724569-5f546fd6f2b5) |
| The rusty hand pump: `ref-pump`, `pump-same`, `pump-same-part`, `docs-vs-pump` | Jorge Montardo | [photo-1771619643236-5f710672c3be](https://images.unsplash.com/photo-1771619643236-5f710672c3be) |
| The white files: `ref-docs`, `docs-same`, `docs-same-tilted`, `breaker-vs-files` | Beatriz Pérez Moya | [photo-1468779036391-52341f60b55d](https://images.unsplash.com/photo-1468779036391-52341f60b55d) |
| `docs-vs-shelf` and `pump-vs-water` | PhilCreates and Gowtham AGM | the warm room and the running water above |

**The held-out photo set** (`evals/heldout/photos/`, used only by `evals/run_heldout.py` and the live checks, never shown in the app) is 44 photographs from The Metropolitan Museum of Art's Open Access collection ([its image policy](https://www.metmuseum.org/policies/image-resources)), public domain under CC0, plus two copies of them made darker and blurred. Every file, its object and the Met's own image name is listed in [`evals/heldout/SOURCES.md`](evals/heldout/SOURCES.md). The live checks' walk-through (made by [`scripts/make_test_walkthrough.py`](scripts/make_test_walkthrough.py)) shows two of them, a padlock (object 468867) and a clock (object 14298), so the Met's other photographs of them can stand in for a family member's own photo. The bank card in that walk-through's cupboard is drawn by the script: a made-up bank ("SAMPLE TEST BANK"), the public test number 4111 1111 1111 1111 and a made-up name.

## Fonts

| Font | Designer | Licence |
|---|---|---|
| Outfit | Rodrigo Fuenzalida | SIL Open Font License 1.1 |
| Yaldevi (Sinhala) | Mooniak | SIL Open Font License 1.1 |

Both are self-hosted through `@fontsource-variable`, so no font request leaves the app.

The diagrams and charts in `docs/diagrams` are set in **Inter** (Rasmus Andersson, SIL Open Font License 1.1), rendered into the PNGs; the SVGs name it and fall back to the reader's system fonts.

## Meta models and libraries

| What | By | Licence or terms |
|---|---|---|
| Muse Spark 1.3, Muse Wonder 1.0, SAM 3.1, Muse Voice Transcribe, Muse Image (Meta Model API) | Meta | Meta Model API terms |
| Muse Spark Open (open weights, served by Fireworks AI) | Meta | Its model licence |
| Omnilingual ASR (`omniASR_LLM_1B_v2` on a GPU, `omniASR_CTC_1B_v2` on a CPU; Sinhala) | Meta | Apache 2.0 |
| `meta-sam-parser`, `@meta-sam/parser`, `@meta-sam/react` | Meta | SAM License |
| React | Meta | MIT |

## Open-source code

| Library | Licence |
|---|---|
| FastAPI, Starlette, Uvicorn, Pydantic, HTTPX, python-multipart | MIT / BSD |
| OpenAI Python SDK (used as the client for Meta's OpenAI-compatible API) | Apache 2.0 |
| itsdangerous | BSD-3-Clause |
| Pillow | MIT-CMU (HPND) |
| NumPy | BSD-3-Clause |
| FFmpeg (called as a program) | LGPL 2.1+ |
| Vite, TypeScript | MIT, Apache 2.0 |
| Lucide icons | ISC |
| qrcode | MIT |
| axe-core (accessibility tests) | MPL 2.0 |
| Playwright (end-to-end tests, screenshots, rendering the charts) | Apache 2.0 |
| Mermaid and its CLI (the diagrams in `docs/diagrams/src`) | MIT |
| eSpeak NG (called as a program, only by the live checks, for their synthetic voices) | GPL 3.0 |
| `huggingface_hub` (only `deploy/huggingface/push.py`) | Apache 2.0 |
| fairseq2, PyTorch, kenlm (the Sinhala speech service) | MIT, BSD-3-Clause, LGPL 2.1 |

## Speech data used for measurement

The Sinhala speech service was measured on [OpenSLR SLR30](https://www.openslr.org/30/), *High quality TTS data for Sinhala*, collected by Google in Sri Lanka (Copyright 2015, 2016 Google, Inc., CC BY-SA 4.0). The recordings are not included in this repository; `evals/results/sinhala_asr-*.json` keeps their transcripts beside what the model heard, under the same licence. The live Sinhala check (`frontend/tests/live_full.cjs`) asks the help line one of these recordings out loud (`sin_9228_2840141256`), and its report keeps the transcript and what was heard, under the same licence.

## Facts and figures

- Departures for foreign employment in 2025: 310,915, after a record 314,672 in 2024; the 2026 target of 350,000; remittances of about US$7.8 billion in 2025; and the departures by country. Sri Lanka Bureau of Foreign Employment figures, reported by the [Daily Mirror, 6 January 2026](https://www.dailymirror.lk/breaking-news/Sri-Lanka-eyes-350-000-foreign-employment-departures-in-2026/108-329575). "About 850 a day" and "seven in ten to Kuwait, the UAE, Qatar or Saudi Arabia" are worked out from these figures.
- Departures for foreign employment, January to August 2025: 212,302 people, 82,050 of them women. Sri Lanka Bureau of Foreign Employment figures, reported by the [Daily Mirror, 10 September 2025](https://www.dailymirror.lk/news/Over-212-000-Sri-Lankans-depart-for-foreign-jobs-in-first-eight-months/239-318967).
- The Family Background Report (2013 to 2022): the [HELVETAS policy brief, October 2017](https://www.helvetas.org/Publications-PDFs/Asia/Sri-Lanka/HELVETAS%20Policy%20Brief%20%E2%80%9CThe%20FBR%20Raising%20or%20Lowering%20the%20Social%20Costs%20of%20Labour%20Migration%E2%80%9D%20%28October%202017%29.pdf), and its removal, [Daily FT, 29 June 2022](https://www.ft.lk/news/Cabinet-approves-removal-of-mandatory-family-background-report-for-female-migrant-workers/56-736836).
- Theme 1 of the hackathon, *Build for Your World*, quoted from the [event page](https://dev.meta.ai/events/global-hackathon).
- Emergency numbers shown in the app: Fire and rescue 110, Ambulance (Suwa Seriya) 1990, Police 119.

## The sample home

The Rathnayake family, their home and everything they say are invented for the demo. Any likeness to a real family is a coincidence.
