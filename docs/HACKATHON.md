# Meta Global AI Developer Hackathon: submission notes

- **Project**: If I Disappear
- **Builder**: Nipun Dilshan Senevirathne (individual)
- **Track**: Indie developer
- **Theme**: Theme 1, Build for Your World: *"Bring Meta's models into your domain. Solve a problem you know firsthand, free up time and mental space, and make something possible that wasn't before."*
- **Event**: Meta and Cerebral Valley, online, 26 October to 4 November 2026. Submissions close **4 November, 9:00 PM ET** (5 November, 01:00 UTC; 6:30 AM on 5 November in Sri Lanka). Judging runs 4 to 8 November.

## In one line

When a parent leaves Sri Lanka to work abroad, If I Disappear turns one walk through the house into checked, bilingual handover steps, and proves before they leave that someone at home can really do each job.

## Short description (for the form)

310,915 Sri Lankans left for work abroad in 2025, and every one left a home that still has to run: the main switch in a power cut, the water pump, the gas, the bills, the deeds, the school pickup. If I Disappear lets the person leaving film the house once while explaining it, in Sinhala or English. Muse Spark reads the walk-through into small facts with the exact words said; code finds each quote word for word, SAM 3.1 has to outline the same object Muse Spark points at, and Muse Wonder re-reads every electricity, gas and fire fact. Sinhala speech comes from Meta's open-weights Omnilingual ASR, self-hosted. Then each person staying proves each job: they photograph the object and explain it in their own words. The board answers the real question, "if I left tomorrow, what would stop?", and simulates every day of the absence. While away, a help line on the web and WhatsApp answers only with what was recorded. Models read; code decides; every step is in a hash-chained log. One whole walk-through on Meta's Model API costs $0.34.

## The judging rubric, and where to see each part

The official rubric has four criteria. The top five projects in each track go on to final judging, where the judges watch the video demos live.

| Criterion | Weight | Where to see it |
|---|---|---|
| **Impact**: real-world potential, who benefits, could it become something people use, does it fit a listed problem statement | 30% | A large, specific problem from the builder's own country, the one Theme 1 asks for ([README: the problem](../README.md#the-problem)). Designed for the people who live it: Sinhala as a first language, grandparents' reading sizes, works offline, QR stickers on the objects, WhatsApp for people who won't install anything ([DESIGN.md](DESIGN.md)). Cheap enough to give away: $0.34 for a whole live walk-through ([MODELS.md](MODELS.md#cost)). |
| **Use of Meta AI tooling**: how creatively Meta's tools are used, beyond basic integration | 25% | Seven Meta models, each doing what it is best at, cross-checking each other: Muse Spark's point must fall inside SAM 3.1's mask; Muse Wonder re-reads safety facts and may only uphold or flag; SAM 3.1 tracks the object through the clip from Muse Spark's point; SAM 3.1 frames both photos before Muse Spark compares them; Omnilingual ASR brings Sinhala, which Meta's hosted speech model doesn't offer, measured on 189 real recordings. What surprised us, good and bad: [README](../README.md#what-surprised-us), [MODELS.md](MODELS.md), [EVALUATION.md](EVALUATION.md#what-real-runs-taught-us). |
| **Technical depth and execution** | 20% | Three-witness verification with a pinned policy, a hash-chained event log and pure projection, three-valued coverage, a day-by-day absence simulation, an exact knapsack teaching plan, a fenced tool-calling agent, signed scoped links, spending caps that hold across threads and processes, strict CSP, recordings sent in resumable pieces ([ARCHITECTURE.md](ARCHITECTURE.md), [diagrams](diagrams/README.md)). 230 backend tests, 5 service tests, 136 browser checks (118 on the sample home, 18 on the live screens), and a golden replay. |
| **Demo**: a working demo that holds up live, and a video that is good to watch | 25% | The sample home runs with no key, and every check and decision in it is live code ([JUDGES.md](JUDGES.md)). The whole web app ran live on Meta's Model API, the way a family uses it, in English and in Sinhala: 76 of 76 checks each, about fifty cents a run ([EVALUATION.md](EVALUATION.md#the-whole-web-app-live)). The API-level live check passed on the final code for $0.34. The same runs on the hosted copy, every failure kept: [the hosted copy](EVALUATION.md#the-hosted-copy-1-november). The video script below is written for judges watching live. |

## Before submitting

Done:

- [x] Day-one checks against Meta's Model API (`scripts/check_meta_api.py --video --wav …`): all passed; the report is `evals/results/api_check-meta.json`.
- [x] The sample home re-recorded on Muse Spark 1.3, Muse Wonder 1.0 and real SAM 3.1 runs, with its photos made by Muse Image.
- [x] The evaluation run on Muse Spark 1.3 and on Muse Spark Open ([EVALUATION.md](EVALUATION.md)), and run again on both on 1 November on the final code.
- [x] Four held-out sets (photo pairs, walk-through transcripts, explanations, help questions) written and frozen before their first run, each run with and without the part of the app it tests; the photo pairs run three times, and a fourth after the comparison prompt changed.
- [x] A live walk-through through the real server, three times (`scripts/live_check.py`). The first two runs changed the speech, privacy, tracking and reading code; the third passed every step for $0.36, and on 1 November, on the final code, all 10 facts verified for $0.34.
- [x] The whole web app, live on Meta's API, in a real browser (`frontend/tests/live_full.cjs`), with the app in English and in Sinhala: 76 of 76 checks each. Its runs found and fixed the problems listed in [EVALUATION.md](EVALUATION.md#the-whole-web-app-live-29-october-to-1-november).
- [x] Sinhala speech measured on real Sinhala voices (189 public clips, 12 speakers): 12.4% character error rate on CPU.
- [x] Hosted on Hugging Face Spaces, one command each (`deploy/huggingface/push.py`; Docker Spaces need a PRO account), and tested there on 1 November: 118 of 118 browser checks (the guided tour included), the API live check, the whole web app live four times in English and Sinhala, and the Sinhala Space ([what was tested](../deploy/huggingface/README.md#what-was-tested-on-the-hosted-copy)).
- [x] Before that, both images were built and run as a Space runs them: the app passed all 78 browser checks, and in live mode the 13 live-screen checks; rebuilt on 1 November, all 101 and all 18.
- [x] The diagrams folder: 15 diagrams and 5 charts, drawn from the result files ([diagrams](diagrams/README.md)), and the README written around the rubric.

Still to do, in this order:

1. **Put your own Meta key on the Space.** The development key used for the tests was taken off it. Make a fresh key, then on the Space's page open **Settings → Variables and secrets**, add the secret `MODEL_API_KEY`, and restart the Space. Until then the sample home works and real homes can't start. `https://nipun-dilshan-if-i-disappear.hf.space/try` is the link for the form.
2. **Record one real walk-through.** On your phone, open `https://nipun-dilshan-if-i-disappear.hf.space/start`, enter the invite code, keep the private link it gives you, and record from **Record** (your own home, one or two rooms at a time, in Sinhala). It goes in the video, and it is the one test the evaluation still lacks. The Space's disk is wiped when it restarts, so record, review and prove in one sitting. On the Space's two CPUs, Sinhala speech takes about twice the video's length to hear, and the moving outlines on the clips come 5 to 10 minutes after the review, so allow about half an hour.
3. **The invite code for judges (optional).** To let them record a home of their own, put the code in the submission form's private notes, not in the public README. The spending caps ($5 a day, $25 in all, set by `--live`) hold either way.
4. **WhatsApp (optional).** Meta's free test number, up to five verified family numbers; set the four `WHATSAPP_*` variables and point the webhook at `/webhooks/whatsapp`.
5. **Record the demo video** from the script below. Upload it (YouTube, unlisted, or wherever the form asks) and add the link at the top of the README.
6. **Push the repository** and submit the form with the live link, the video and the repository.
7. **Revoke the development keys** used to build and deploy this (the Meta Model API key, the Fireworks key and the full-access Hugging Face token), and make fresh ones: a Meta key for the Space, and a write-only token for any later deploy.

## Demo video script

About 2 minutes 50 seconds; check the form for the official limit. At the final stage the judges watch the videos live, so the first fifteen seconds have to land, every Meta model has to be visible doing its job, and it has to be obviously the real app.

| Time | On screen | Say |
|---|---|---|
| 0:00 | Dark room. A phone torch finds a switch box. Caption: *310,915 Sri Lankans left for work abroad in 2025.* | "Every day, about 850 Sri Lankans leave to work abroad. Each of them leaves a house that still has to run." |
| 0:10 | Quick cuts: the pump, the gas cylinder, a cupboard of files | "The main switch, the water pump, the gas, the deeds. It all lives in one person's head, and it gets handed over in a rush, the week before the flight. Nobody knows who can really do what, until something breaks." |
| 0:25 | Your own phone footage: you walk to the switch box and explain it in Sinhala. Then the Record page uploading it | "If I Disappear asks for one thing. Film the house once, and explain it, in Sinhala or English." |
| 0:40 | Review: one fact opened, its quote, its time, the still. Lower third: **Muse Spark 1.3** | "Muse Spark reads the walk-through into small facts, each with the exact words she said, the second she said them, and a point on the frame." |
| 0:52 | The same fact: the SAM 3.1 outline, Muse Spark's point inside it, then Muse Wonder's reason. Lower thirds: **SAM 3.1**, **Muse Wonder 1.0** | "Then three witnesses check every fact. Code finds her exact words. SAM 3.1 has to outline the same object Muse Spark pointed at: two Meta models that never see each other's answer have to agree on the pixels. For electricity, gas or fire, Muse Wonder reads it again." |
| 1:12 | The white files fact: the point beside the outline. Then **Not used**: the medicine sentence | "When they disagree, the app doesn't guess. It waits for her. And some things it won't hold: medicine instructions never become steps." |
| 1:22 | The board: 4 of 6, the first problem on 20 November. Scroll to the day-by-day simulation and the teaching plan | "Then the question every family asks. If she left tomorrow, what would stop? Four of six jobs. The first problem lands on the day she leaves." |
| 1:35 | Prove: Nethum, Water pump. **A different one** doesn't pass ("Couldn't tell from this photo: I couldn't find a water pump"). **The right one** passes, the outline and what matched | "So the people staying prove it. A photo with no pump in it can't pass: the app asks for another. The right one passes: SAM 3.1 finds the pump, and Muse Spark names what matches the pump she showed: the finned motor, the bolted flange, the terminal box." |
| 1:55 | Tell me: the first answer fails (missed the grinding noise), the second passes, the board drops to 3 of 6 | "Then he explains it, in his own words. He forgets what to do if it grinds, so it fails. He tries again, and the pump turns green." |
| 2:10 | Help: *"The pump is making a grinding noise"* gives her recorded steps and clip. *"I can smell gas"* gives 110, 1990, 119. Then WhatsApp in Sinhala | "When she's gone, they ask. The answer is only ever what she recorded. A gas smell is an emergency, so code shows the numbers first, before any model runs. In Sinhala, on WhatsApp too." |
| 2:28 | The fridge card, a QR sticker on the pump, scanned on a phone that saved the offline pack, in airplane mode | "Stickers go on the objects. Scan one and it opens that one job, even with no signal." |
| 2:38 | Evidence: "The chain is intact". Then the terminal: the live check passing, $0.34. Caption: *371 automated checks* | "Models read, code decides, and every step is in a log anyone can check. One whole walk-through on Meta's API: thirty-four cents." |
| 2:50 | The landing page: *When you're away, what you know stays home.* The live link and the repository | "If I Disappear. When you're away, what you know stays home." |

**Recording tips**

- Record the app at phone size (Chrome's device toolbar at 390 × 844, or the phone's own screen recorder) at 1080p. Use the sample home for everything after 0:40: it never waits on a model, so it holds up live.
- Burn in captions; judges may watch without sound. Name each Meta model on screen the moment it acts.
- Hold each screen at least two seconds, and zoom in on the SAM 3.1 outlines and Muse Spark's point: they are the moment the cross-check becomes visible.
- Speak the Sinhala line yourself at 0:25; it is the one shot only you can film, and the strongest proof that this is built for its world.
- Never show a key, a token or an owner link on screen.

## Build log

**28 October 2026.** The whole app, in one long day:

- Backend: the model client (retries, circuit breaker, daily and lifetime spending caps), the walk-through pipeline, the three witnesses and the pinned policy gate, the hash-chained ledger, the engine (jobs, coverage, simulation, teaching plan, gaps), show-me and tell-me proofs, the fenced help agent, the WhatsApp webhook, signed links and QR stickers, privacy scrubbing, muting and blurring.
- Web app: React 19, English and Sinhala throughout, light and dark themes, an offline pack, print layouts for the fridge card and stickers, a strict Content-Security-Policy.
- Morning: every prompt tested on Muse Spark Open (Meta's open-weights Muse Spark, on Fireworks AI). Its runs found most of the problems listed in [EVALUATION.md](EVALUATION.md), and the code and prompts changed for each.
- Afternoon, with the Meta Model API key: day-one checks of every call; SAM 3.1 disagreed with the stock photos, so the sample home's photos were remade with Muse Image; the sample home re-recorded on Muse Spark 1.3, Muse Wonder and SAM 3.1; the evaluation run on both models.
- Evening: a live check of the whole server on Meta's API, three runs. They found that long speech turns over-muted a spoken secret, that a debug folder kept raw model output after a household was deleted, that one object was tracked once per fact, and that the owner's own name for the switch box confused SAM 3.1. Each was fixed and tested; the third run passed every step.
- Night: Omnilingual ASR measured on 189 public Sinhala recordings on CPU (12.4% character error rate with `omniASR_CTC_1B_v2`). The runs found two broken installs and two Sinhala text problems: the joiner inside conjunct letters, and Sinhala written in other alphabets. All four were fixed and tested. Then hosting on Hugging Face Spaces, with both images built and run as a Space runs them.

**29 October 2026.** The diagrams folder: 15 diagrams and 5 charts, each number read from the result files. The README rewritten around the official rubric. Checking the README's claims found two things in the web app: a sticker never showed its clip (it asked for the recording under the sample's own household id, not the link's), and a sticker didn't open offline. Both fixed, and the offline checks now cut the connection for real: the browser's offline switch doesn't reach the service worker, so the old check could pass without it. The landing and review pages said every fact has three witnesses; they now say up to three, as the rules do. The 90-second recording and the screenshots were made again from the fixed app. Asked whether the hosted copy is fully working with a key, the honest answer found two more gaps: there was no screen to start a real home (only a command), and uploads stopped at 200 MB, which a phone's 1080p video passes in about a minute and a half. Now the Start page makes a home with the invite code, a recording goes up in resumable 8 MB pieces (up to 1 GB), the phone says when a video is too big before sending it, and `push.py --live` sets the key as a secret with the invite code and a lifetime cap. 125 backend tests, 4 service tests and 91 browser checks pass; the golden replay rebuilds the sample board byte for byte.

**29 October, later.** An outside review of the code listed problems. Each one was reproduced against the code before anything changed (`backend/tests/test_review_findings.py`: every test in it failed on the code as it was), and only the confirmed ones were fixed: a sticker's link now opens only its own job, its own clip and still, and can't ask the help line; a family link can't read facts the owner hasn't reviewed; a removed person's link stops at once; one access matrix (`scope.py`) decides who sees what, with a test for every role; a job's clip is cut for that job, with the words of facts the owner didn't accept silenced; an owner's edit and a help question are scrubbed and ruled like a recording; a changed step makes its proof stale; a failed step leaves nothing of the upload behind; spending reserves the most a call can cost across processes, and one circuit breaker is shared by every request; the simulation covers a two-year absence. Then four held-out sets were written and frozen, and run on Meta's API with and without the part of the app each one tests.

**29 to 31 October.** The whole web app, live: `frontend/tests/live_full.cjs` records a test walk-through on the Record page and does everything a family does after it, on Meta's API. Its runs found that SAM 3.1 missed a bank card in the smaller video the app keeps (the privacy search now runs on a 1280-pixel copy of the upload), that the Sinhala written inside the long reading call was often garbled (a short Sinhala call of its own now writes it, used only when well formed), that checking facts one after another took 85 seconds (now 26), that the WhatsApp preview and the real line answered in different languages, that a PIN typed into the help line was shown back as typed, and that the Sinhala speech service stopped answering its health check while it worked. Each was fixed and tested.

**1 November.** The final runs, on the final code. A spoken answer sent as a WAV file failed with a server error; looking into it found that every upload left a file descriptor open, and that ffmpeg would have opened an "upload" that was really a playlist or a concat script naming the server's other files (now it opens only audio and video, from disk). Checking a photo or a spoken question ran on the server's event loop, so the whole server stopped answering while it did (now on worker threads, as are the WhatsApp replies); a spoken question nobody could make out was answered as an empty one (now it is asked again); and three Sinhala translations that passed every witness had mistakes an owner reading in English never saw (the review card now shows the other language, and a fix to the translation alone keeps her own words). Every fix has a test. Then: the whole web app live, 76 of 76 checks in English and 76 of 76 in Sinhala; the API live check, 10 of 10 facts verified for $0.34; the model suites again on Muse Spark 1.3 and Muse Spark Open; the held-out photo pairs three times; and the app's image rebuilt and run as a Space runs it. 221 backend tests, 5 service tests, 101 browser checks and 18 live-screen checks pass.

**1 November, the hosted copy.** Hugging Face now asks for a PRO account for Docker Spaces, so the deploy waited for one.
- **Deploy.** The Sinhala service went up on its own basic CPU, joined to the app with a token. Then the app, with the invite code, the link key, the spending caps and a development key as secrets.
- **What testing it from outside found**, that the local runs couldn't:
  - a saved home opened offline as a blank page (the Space adds `Vary: origin` to every response);
  - the next visitor's clean-up deleted every other visitor's untouched copy of the sample;
  - on two CPUs a sticker's clip took up to 100 seconds and saving offline two minutes;
  - a WhatsApp reply linked to localhost;
  - Muse Spark called the walk-through's clock a different clock, because the still from the video was darker than the new photo.
- **Each was fixed** and the app pushed again. The clock took one sentence in the comparison prompt, measured on the same two crops (4 of 4 against 2 of 4) and on the 29 photo pairs a fourth time (no different object confirmed).
- **Results there:**
  - 118 of 118 browser checks on the final build, the guided tour included (102 of 102 on the builds before it);
  - the API live check passed for $0.34;
  - the whole web app live: 71 and 72 of 74 in English and 73 of 74 in Sinhala before the prompt change, 74 of 75 in English after it;
  - a Sinhala walk-through nobody could make out, through the Sinhala Space: 10 of 10.
- **The test machine's own misses.** Two answers in English run 2 were cut at 30 seconds by the test machine's browser connection, and run 3's one miss was a download dropped when its network proxy restarted.
- **Speed.** Sinhala speech runs at about half real time on the Space's two CPUs.
- **Afterwards**, the development key was taken off the Space.

Making the video's frames found two more problems:
- a bank card coming in at the frame's edge showed eight digits for three seconds before SAM 3.1 found it (now blurred from that edge);
- the board's timeline said "week by week" over monthly bars.

**1 November, evening: a guided tour.** Judges have minutes, so the sample home now opens with a tour.
- **Where:** it opens on a first visit, on the landing page or the sample home.
- **What:** fourteen steps, from the board to the evidence. Each one opens its page, spotlights the part it explains, names the Meta models at work there, and suggests one thing to try.
- **How it behaves:** the dimmed area lets clicks through. It works with the keyboard and at phone size. A compass button in the top bar starts it again.
- **Tested:** sixteen new browser checks walk every step on the hosted copy: 118 of 118.

**2 to 4 November.** Planned: a real walk-through in a real home, the demo video, submission.
