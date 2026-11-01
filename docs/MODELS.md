# Meta's models in If I Disappear

Seven Meta models, each doing the one thing it is best at, and none of them making a decision on its own. Every prompt is in [`backend/app/meta/prompts.py`](../backend/app/meta/prompts.py) and every JSON schema in [`spark.py`](../backend/app/meta/spark.py), so they can be read in one place.

| Model | API | What it does here | Without it |
|---|---|---|---|
| **Muse Spark 1.3** (`muse-spark-1.3`) | Meta Model API, chat completions | Reads each walk-through into claims; compares a family member's photo with the owner's; checks a spoken explanation point by point; runs the help agent's tool loop | Judge mode replays recorded outputs; the help line falls back to code retrieval |
| **Muse Wonder 1.0** (`muse-wonder-1.0`) | Meta Model API, chat completions | The second reading of electricity, gas and fire facts | Muse Spark does the second reading instead |
| **SAM 3.1** (`sam-3.1`) | Meta Model API, Responses API and Files API | Outlines the object at Muse Spark's point (the pixels witness); tracks it through the clip; finds the object in a family member's photo; finds cards and screens to blur | Object facts can't be verified and wait for the owner (the gate fails closed) |
| **Muse Voice Transcribe** (`muse-voice-transcribe-1.0`) | Meta Model API, `/v1/asr/transcribe` | English speech to text, a piece between pauses at a time, with the family's names as keywords | English recordings and voice questions are off |
| **Omnilingual ASR** (`omniASR_LLM_1B_v2` on a GPU, `omniASR_CTC_1B_v2` on a CPU) | Open source (Apache 2.0), self-hosted in `services/sinhala-asr` | Sinhala speech (`sin_Sinh`) to text, in clips under 40 seconds cut at pauses. Measured on real Sinhala voices: 12.4% character error rate on CPU | Sinhala recordings are off; typed Sinhala still works |
| **Muse Image** (`muse-image-1.0`) | Meta Model API, Responses API | Made the sample home's photos (`scripts/make_sample_photos.py`) | — (never used on a family's handover) |
| **Muse Spark Open** (`accounts/fireworks/models/muse-spark-open`) | Meta's open weights, served by Fireworks AI | The development model, and the second column of the evaluation | — |

## Checked on day one

`scripts/check_meta_api.py` makes one small real call for each thing the app depends on and writes `evals/results/api_check-meta.json`. On 28 October 2026, with the hackathon key:

| Check | Result | What came back | Cost |
|---|---|---|---|
| Model list (`/v1/models`) | passed | all of `muse-spark-1.3`, `muse-wonder-1.0`, `sam-3.1` listed (also `muse-image-1.0`, `muse-voice-transcribe-1.0`) | $0.0000 |
| Strict JSON schema, English and Sinhala | passed | "Resetting tripped breaker" / "බ්‍රේකර් එක දැමීම", safety electricity | $0.0025 |
| An image in, a point out | passed | the point (0.38, 0.59), on the breakers | $0.0041 |
| Tool calling (`tool_choice: auto`) | passed | called `search_steps` with "power went off" | $0.0012 |
| Prompt caching | passed | 2,417 cached input tokens on the repeat | $0.0159 |
| Muse Wonder second reading | passed | uphold: "The full turn says to find the dropped switch and push it up, which matches the claim." | $0.0170 |
| SAM 3.1 by name | passed | "electrical panel": the whole box, confidence 0.64; "circuit breaker": found too | $0.0050 |
| SAM 3.1 by point | passed | one mask at the point | $0.0025 |
| SAM 3.1 tracking through a clip (Files API) | passed | masks on 20 of 20 frames | $0.0100 |
| Muse Voice Transcribe (a 20 s English clip) | passed | the words came back in `PUSH_TO_TALK` mode; a separate `DIARIZATION` call returned timed turns with speakers | $0.0010 |
| Sinhala speech service | skipped | not deployed yet (`SINHALA_ASR_URL` unset) | — |
| WhatsApp Cloud API | skipped | not set up yet | — |

The whole run cost $0.06. The first run of this script, an hour earlier, found the one surprise: SAM 3.1 returned nothing for "circuit breaker" on the stock photo the sample home used then (see below). This run used the sample home's new photo.

## Muse Spark: reading a walk-through

One call per recording, in `spark.compile_claims`:

- **Input**: the household's names, the jobs already known (so a second recording reuses their names), the transcript turns as JSON with times, and up to 40 stills, each labelled with its id and time.
- **Output**: `response_format` with `type: json_schema` and `strict: true`. Every field is required, enums are closed, and there are no nullable unions (absent values are `-1` or `""`), so constrained decoding has one shape to follow.
- **Settings**: `reasoning_effort: "high"`, and a `prompt_cache_key` per household so the long instructions are cached between recordings (the day-one check saw 2,417 cached tokens on a repeat).
- **The 13 rules** in `CLAIMS_SYSTEM`, in order of importance: only what was said; quotes copied character for character in the language spoken; never medical instructions; never guess a hidden secret; one fact per claim, with its kind; one job key, type, safety and name per job, with each job type defined; a plain noun for the segmentation model; a point on the nearest still; the time; safety; faithful English and Sinhala; schedules only on schedule and payment facts, with Monday as 0; contacts.

Each claim then has to survive the three witnesses ([ARCHITECTURE.md](ARCHITECTURE.md#2-three-witnesses-and-a-gate-backendappwitness)).

## Muse Spark: show me, tell me, help

- **Show me** (`compare_photos`): the owner's still and the family member's photo, framed alike by `checks.comparison_pair`: each cropped around what SAM 3.1 found (every instance of the noun, so all the white files rather than one), with room for the surroundings; or both sent whole when the owner's still has no agreed mask. The model answers `same_object`, `matched_features`, `mismatches` and an explanation in both languages. It is told to be strict: if it can't tell, the answer is false. It is also told that the owner's picture is a still from a phone video, softer and in other light, so a different shade, or texture that shows more in one photo, is not a mismatch on its own; a part, label, mark or shape is. Without that sentence it called the walk-through's clock a different clock in 2 of 4 tries, and in both hosted runs that got an answer, because the wood looked darker in the still ([EVALUATION.md](EVALUATION.md#the-hosted-copy-1-november)). Code requires `same_object` *and* two concrete matching features.
- **Tell me** (`check_explanation`): the recorded points and what the family member said. The model answers, per point, `covered` and the exact words that cover it. Code re-checks every quote against the transcript and applies the coverage and safety rules.
- **Help** (`help/agent.py`): `chat.completions` with tools and `tool_choice: "auto"` (the only choice Meta's API supports), at most four turns. The tools are `search_steps`, `answer_with_task` (task key plus a reason in English and Sinhala) and `not_recorded`. Code refuses any task key the search didn't return.

## SAM 3.1

Called through the Responses API with model `sam-3.1`, one noun phrase per request as the docs require, `mask_encoding: one_bit` and `include_confidence: true`, `store: false`. Output is parsed with Meta's official `meta_sam_parser`, never by hand, into masks with bounds, confidence and an SVG path (`meta/sam.py`). An empty answer means nothing was found.

- **By name**: the pixels witness, privacy blurring (`credit card`, `identity card`, `phone screen`) and the show-me photo.
- **Through the clip, from a point**: when the owner accepts the first fact about an object, the clip around it is cut to 5 frames a second (once per object and recording: the four facts about the switch box share one tracked clip), uploaded with the Files API, and SAM 3.1 is prompted with Muse Spark's point (an object prompt built with `build_object_prompt`, not a noun), then tracks the object in both directions. The web app draws the masks over the playing video.

What the name is matters. On day one, SAM 3.1 found nothing for "circuit breaker" in a stock photo of a breaker panel but found the panel as "electrical panel"; it saw a rusty hand pump as a "faucet" and white binders as "books". That is the reason the reading model is asked for the plain name of the whole visible object, and the reason the sample home's photos were remade (below).

## Muse Wonder 1.0: the second reader

`spark.second_reading` gives it the claim, the owner's exact words, the whole turn and, for an object, the still and SAM's box. It can only return `uphold` or `flag`, with a reason in English and Sinhala. It never rewrites anything. The instructions were rewritten once after a real run: the reader was asking to see spoken facts (a phone number "on the fridge") in the frame, and calling facts that were split on purpose incomplete. See [EVALUATION.md](EVALUATION.md).

## Muse Image: the sample home's photos

Stock photos never matched each other or the story: the "water pump" was a rusty hand pump, and SAM 3.1 rightly disagreed with what the owner said about it. So the sample home's five photos (the switch box, a different switch box, the pump and tank, the kitchen with the gas cylinder, the bedroom cupboard with the white files) were generated once with Muse Image (`client.responses.create(model="muse-image-1.0", input=prompt)`, $0.01 an image). The prompts and response ids are in `backend/fixtures/base/photos.json`. After that, SAM 3.1 found every object the owner names, with confidence between 0.62 and 0.96. Muse Image is never used on a family's handover: nothing generated is ever shown as someone's home.

## Speech

- **English**: Muse Voice Transcribe's file endpoint in `PUSH_TO_TALK` mode, with the family's names as keywords. A walk-through is first cut at pauses, as Sinhala is, and the pieces are sent four at a time, so every sentence keeps its own time. The first live run used `DIARIZATION` mode instead: its turns were 16 and 29 seconds long, too long to show the second a fact was said, and one spoken gate code silenced 29 seconds of the video. Questions and explanations are short and are sent whole.
- **Sinhala**: Muse Voice Transcribe has no Sinhala, so the app runs Meta's open-source Omnilingual ASR (language `sin_Sinh`) as a small service: `services/sinhala-asr` (FastAPI; Docker, Modal or a Hugging Face Space, where it runs beside the hosted app). Audio is cut at pauses into clips under the model's 40-second limit. On a GPU it runs `omniASR_LLM_1B_v2`, which is given the language. On a CPU it runs `omniASR_CTC_1B_v2`: on 189 public Sinhala recordings from 12 speakers it had a 12.4% character error rate, 3.2 times faster than real time on the build machine's 2 CPUs ([EVALUATION.md](EVALUATION.md#sinhala-speech-on-real-sinhala-voices)). On a Hugging Face Space's basic CPU it is slower: an 88-second walk-through took about 170 seconds to hear, half real time. Where memory is short, `omniASR_CTC_300M_v2` (15.4%) runs in 1.3 GB; the live web-app runs on the 8 GB build machine used it. CTC models take no language hint, and 9 of those 189 clips came back in another Indic alphabet, so code marks a piece that is mostly not Sinhala letters as not understood: no fact is read from it, and the owner sees it listed.

## Muse Spark Open on Fireworks AI

Before the hackathon's key arrived, the app ran against Muse Spark Open, Meta's open-weights Muse Spark, on Fireworks AI (`MODEL_PROVIDER=fireworks`). It supports the same strict JSON schemas, tool calls, image input and `reasoning_effort`. Every prompt was first tested and changed on it, and its runs found most of the problems listed in [EVALUATION.md](EVALUATION.md). Fireworks has no SAM 3.1, Muse Wonder or speech model, so those steps are off in that mode. The evaluation runs on both.

## Cost

Prices are in `meta/pricing.py` (from Meta's price list, 28 October 2026): Muse Spark 1.3 at $1.25 per million input tokens ($0.15 cached) and $4.25 per million output tokens; Muse Wonder 1.0 at $4.00 / $0.20 / $20.00; SAM 3.1 at $0.0025 per image and $0.0002 per video frame (50-frame minimum); Muse Voice Transcribe at $0.18 per hour; Muse Image at $0.01 per image. Standard mode only: the app never uses Contributor mode, because that lets Meta train on the data, and these are a family's recordings.

What one walk-through really cost, from the household's own log (`cost.recorded` events), in the live check on 1 November on the final code ([`live_check.json`](../evals/results/live_check.json)): a 48-second English video, ten facts, then a help question, an explanation and a photo.

| What | Model | Calls | Cost |
|---|---|---|---|
| Hearing the walk-through, in 10 pieces cut at pauses | Muse Voice Transcribe | 10 | $0.0016 |
| The privacy pass: the whole video searched for credit cards, identity cards and phone screens, two frames a second | SAM 3.1 | 3 | $0.0570 |
| Reading it into 10 facts (high reasoning, with its stills) | Muse Spark 1.3 | 1 | $0.0695 |
| The Sinhala of every fact and job name, in a short call | Muse Spark 1.3 | 1 | $0.0103 |
| The pixels witness, once per object fact | SAM 3.1 | 8 | $0.0200 |
| The second reading of the electricity and gas facts | Muse Wonder 1.0 | 6 | $0.1280 |
| Tracking the three objects through the clip | SAM 3.1 | 3 | $0.0300 |
| One help question (the tool loop; the gas smell is answered by code) | Muse Spark 1.3 | 2 | $0.0040 |
| Checking one explanation | Muse Spark 1.3 | 1 | $0.0046 |
| Checking one photo: finding the pump, then comparing it | SAM 3.1, Muse Spark 1.3 | 2 | $0.0131 |
| **All of it** | | **37** | **$0.3381** |

The largest cost is Muse Wonder's second readings (its output price is about five times Muse Spark's), then the reading and the privacy pass. On 28 October the privacy pass asked SAM 3.1 three names on each of 12 stills, 36 calls for $0.09; it now searches the whole video, three calls for $0.06, and finds what the stills missed. The reading itself costs about seven cents. On the evaluation sets, a help question averaged half a cent and an explanation check a little under half a cent.

The whole web app, live ([EVALUATION.md](EVALUATION.md#the-whole-web-app-live)), cost $0.54 with the app in English and $0.45 in Sinhala: a 71-second walk-through of six rooms, 15 to 18 facts, five objects tracked, four photos and four explanations checked (one spoken), seven help questions (one spoken), a spoken answer to one of the board's questions and two WhatsApp previews.

From these unit costs, a whole handover (say four three-minute walk-throughs, every job proven by three people, and a hundred help questions during the absence) would come to about three dollars. That is an estimate, not a measurement.

Every call is priced before it is made and refused if it would pass the daily cap.
