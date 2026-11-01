# A five-minute tour for judges

No sign-up and no key. Open the app at https://nipun-dilshan-if-i-disappear.hf.space, press **Try the sample home**, and you get your own private copy of the Rathnayake home. Change anything; nobody else sees it, and it is deleted after a day.

**A guided tour opens on your first visit.** Fourteen steps, about three minutes, from the board to the evidence: each step opens its page, spotlights the part it explains, says which Meta model is at work, and suggests one thing to try. Press **Start the tour**, or **Explore on my own** and come back to it with the compass button at the top. The list below is the same journey, in more detail.

Short on time? [`docs/demo/if-i-disappear-demo.mp4`](demo/if-i-disappear-demo.mp4) is a 90-second captioned recording of most of this tour, clicked through in the real app.

Dilini leaves Sri Lanka on 20 November for two years. Kasun (her husband), Seetha Amma (her mother) and Nethum (their son, 14) stay. Dilini walked through the house twice and explained it: once in Sinhala, once in English. Everything the models said about it is a real, recorded run of **Muse Spark 1.3, Muse Wonder and SAM 3.1**; everything the app decided, it decides again, live, as you click.

## What to try, in order

1. **The board.** The headline is the question every family asks: *if Dilini left tomorrow, what would stop?* Four of six jobs. The first problem lands on 20 November: the gas cylinder, because nobody has shown they know who to call. Scroll down for the day-by-day simulation of the absence, the teaching plan for the days before she leaves, and two questions Dilini didn't answer yet.
2. **A job.** Open **Main switch box**. Each step shows Dilini's own Sinhala words under the English, with the second she said them. Press play: the clip starts at that moment, and SAM 3.1's outline follows the switch box through it. Kasun is marked as proven: he showed it and explained it.
3. **Prove it.** Go to **Prove**, pick **Nethum** and **Water pump**.
   - Tap **A different one**: a photo of running water. SAM 3.1 finds no water pump in it, so it doesn't pass: the app says it couldn't tell from this photo, and asks for another, from the front, closer, with more light. (A photo of a *different* pump would be called a different one.)
   - Tap **The right one**: SAM 3.1 outlines the pump, and Muse Spark matches it to the one Dilini showed, listing what matched (the blue motor's cooling fins, the bolts on the concrete plinth, the pipe above it).
   - Tap the answer that starts **"I switch the pump on…"**: it fails. He forgot what to do if it grinds, and who to call.
   - Tap the answer with **"grinding noise"**: every point is covered, the job turns green, and the board drops to three of six.
4. **Help.** Ask *The pump is making a grinding noise*: the answer is Dilini's recorded pump steps, never new advice. Ask *I can smell gas in the kitchen*: code treats it as an emergency before any model runs, and shows Sri Lanka's 110, 1990 and 119. Ask *How do I fix the washing machine?*: nothing was recorded, so it says so. Try the WhatsApp preview in Sinhala: *කරන්ට් ගියා, මොකද කරන්නේ?*
5. **Review.** Two facts are waiting for Dilini, and for you:
   - *The number is on the fridge* (the gas shop's number, from the Sinhala walk-through). It passed every witness: her exact words were found, Muse Spark pointed at the fridge and SAM 3.1 outlined the same fridge, and Muse Wonder upheld it. Accept it.
   - *The white files hold Nethum's school records.* Here two Meta models disagreed: Muse Spark pointed just beside the files, on the cupboard's wooden frame, about 30 pixels from the nearest file SAM 3.1 outlined. The rules don't guess; the fact waits, with both shown on the frame, until a person decides.
   - Open **Not used**: Dilini also said *"Amma takes half a tablet of her pressure medicine every morning."* No fact was made from it, and code says why: the app never turns medicine instructions into steps.
6. **Evidence.** Every step of the sample is in a hash-chained log: each model output, each check, each decision, and who made it (`recorded:muse-spark-1.3`, `recorded:muse-wonder-1.0`, `recorded:sam-3.1`, `code`, `owner`). The chain check runs live.
7. **Card.** The fridge card and a QR sticker for each object. Open a sticker's link in a private window: it opens only that job and its clip, never the whole home. Save the offline pack, turn off your connection, and the board still opens, and so does any sticker scanned on that phone.
8. **සිංහල.** Switch the language at the top. Every screen, every fact and every check reads in Sinhala.
9. **The rules.** `/rules` shows the policy the code follows, and its SHA-256 matches the one pinned in the code. If the file changes, the server refuses to start.

## What is real in the sample home, and what is sample data

| Part | In the sample home | In a real home |
|---|---|---|
| Reading each walk-through into facts | **Real** recorded Muse Spark 1.3 runs | Muse Spark 1.3 |
| Second reading of electricity, gas and fire facts | **Real** recorded Muse Wonder 1.0 runs | Muse Wonder 1.0 |
| Outlines on the stills, tracking through the clips, masks on the family's photos, the privacy pass | **Real** recorded SAM 3.1 runs | SAM 3.1 |
| Photo comparisons, explanation checks, help answers | **Real** recorded Muse Spark 1.3 runs | Muse Spark 1.3 |
| Every check and decision (words, pixels, rules, board, proofs) | **Real**: the app's code runs live as you click | The same code |
| The house | Photos made with Muse Image (plus two Unsplash photos), turned into walk-through clips | The family's own video |
| Speech | Sample transcripts (the clips are made from photos and have no sound) | Muse Voice Transcribe (English), Omnilingual ASR (Sinhala) |
| The family's photos and answers | Written for the demo; the photos are crops of the house photos | Taken and spoken by the family |
| Dilini's accept and reject decisions | Made for the demo, marked `owner` | Hers |

Every recorded run is saved in `backend/fixtures/recorded/`, with the model that made it and when, and `scripts/build_sample.py` rebuilds the whole sample from them. The same app was first built and measured on Muse Spark Open (Meta's open-weights Muse Spark, on Fireworks AI); those runs are kept in `evals/runs/` and its numbers are in [EVALUATION.md](EVALUATION.md) beside Muse Spark 1.3's.

## With your own Meta Model API key

```bash
cp .env.example .env          # put the key in MODEL_API_KEY
python scripts/check_meta_api.py --video
docker build -t if-i-disappear . && docker run -p 8080:8080 --env-file .env -v iid-data:/data if-i-disappear
```

With `IID_ADMIN_TOKEN` set in `.env`, `IID_ADMIN_TOKEN=… python scripts/live_check.py` (it needs ffmpeg and espeak-ng) then sends one walk-through through that server end to end, from upload to help line, and prints every fact, check and cost (about thirty-five cents; its last run is in [EVALUATION.md](EVALUATION.md#one-live-walk-through-end-to-end)).

The whole web app, live, the way a family uses it (`frontend/tests/live_full.cjs`, about fifty cents): it makes a test walk-through of six rooms with a synthetic voice, a made-up bank card on a shelf, a gate code and a medicine sentence said aloud, then records it on the Record page, reviews, proves (photos and explanations, typed and spoken), asks the help line and the WhatsApp preview, opens stickers and person links, saves the home offline and opens it with the server out of reach, and deletes it. Its last runs are in [EVALUATION.md](EVALUATION.md#the-whole-web-app-live). It also runs against a hosted copy: set `BASE` to its address and leave out `DATA_DIR`, and the two checks that read the server's data folder are skipped ([the runs on the project's own Space](EVALUATION.md#the-hosted-copy-1-november)).

```bash
python scripts/make_test_walkthrough.py walk en       # needs ffmpeg and espeak-ng
BASE=http://127.0.0.1:8080 INVITE=<IID_ADMIN_TOKEN> DATA_DIR=<the server's IID_DATA_DIR> \
  VIDEO=walk/walk-en.mp4 SCRIPT=walk/walk-en.json node frontend/tests/live_full.cjs
```

To record a home of your own, open `/start`: the name of the home, who is leaving, the language, the dates, and the invite code (`IID_ADMIN_TOKEN`). New live homes are invite-only by default (`IID_ALLOW_PUBLIC_LIVE`), so a public copy can't run up a bill, and the daily and lifetime spending caps stop calls before they are passed. The page gives back the owner's private link; then **Record** on a phone sends the walk-through up in pieces, and the rest of the app works on it.
