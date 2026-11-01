# Sinhala speech service

Meta's Muse Voice Transcribe covers 25 languages but not Sinhala, so If I Disappear sends Sinhala
walk-throughs to Meta's open-source [Omnilingual ASR](https://github.com/facebookresearch/omnilingual-asr)
(Apache 2.0, 1,600+ languages), run as this small service. The backend cuts Sinhala audio at
pauses into clips under 40 seconds (`backend/app/media/vad.py`) and posts them here:
`POST /transcribe` with `lang=sin_Sinh` and one `audio` field per clip, answered with
`{"texts": [...]}` in the same order.

## Measured on 28 October 2026

On public Sinhala recordings: [OpenSLR SLR30](https://www.openslr.org/30/), collected by Google in
Sri Lanka (CC BY-SA 4.0), 189 clips from 12 speakers, 18.6 minutes in all. On this repository's
build machine: 2 CPUs and no GPU. [`check.py`](check.py) reproduces it against any running service.

| Model | Download | Character error rate | Clips heard in another alphabet | Speed on 2 CPUs |
|---|---|---|---|---|
| `omniASR_CTC_300M_v2` | 1.3 GB | 15.4% (10.7% on the other clips) | 12 of 189 | 5.7 times faster than real time |
| `omniASR_CTC_1B_v2` | 3.9 GB | **12.4%** (8.8% on the other clips) | 9 of 189 | 3.2 times faster than real time |
| `omniASR_LLM_1B_v2`, the default | 9.1 GB | not measured: too big for this machine's 8 GB of memory | | |

On a Hugging Face Space's basic CPU (two shared vCPUs) it is slower. Through the hosted app on
1 November, `omniASR_CTC_1B_v2` took about 170 seconds to hear an 88-second walk-through: about
half real time.

Word error rates were 55.1% and 46.1%. Sinhala words are long and are joined differently by
different writers, so the character rate is the one to read. The model may have seen SLR30 in
training, so these rates are optimistic. Results: `evals/results/sinhala_asr-*.json`.

What the runs found, and what changed:

- **The install was broken.** A plain `pip install omnilingual-asr==0.2.0` picked pyarrow 26,
  which needs NumPy 2, while fairseq2 needs NumPy 1.x, so the model failed to load. The
  Dockerfile and the Modal app now pin pyarrow 22.
- **A missing joiner.** The CTC models write the zero-width joiner that Sinhala needs inside
  conjunct letters (ත්‍ර) as the tokenizer's unknown mark, `⁇` (*චිත් ⁇ රපට*). The service
  puts the joiner back, and the backend does too, for older services.
- **The right sounds in the wrong alphabet.** CTC models take no language hint, so some clips
  came back in Telugu, Malayalam, Kannada or Gujarati letters, and eSpeak NG's synthetic Sinhala
  voice came back in Latin letters. The app now marks such a piece as not understood: no fact is
  ever read from it, and the review page lists it so the owner can say it again. The LLM models
  are given the language (`sin_Sinh`) and should not do this; that is not measured here.
- **The app's own path works.** Six of these clips joined into one recording, sent through the
  backend's Sinhala path (`speech.transcribe`, cut at pauses, then this service), came back as six
  pieces, each inside its own clip's time, with character error rates from 0 to 16%.

## Running it

| Where | How |
| --- | --- |
| Modal (GPU, scales to zero) | `modal deploy services/sinhala-asr/modal_app.py` |
| Any Docker host with a GPU | `docker build -t iid-sinhala-asr services/sinhala-asr`, then `docker run --gpus all -p 9000:9000 -e SINHALA_ASR_TOKEN=… iid-sinhala-asr` |
| Any Docker host without a GPU, or a Hugging Face Space on its basic CPU | `docker build --build-arg TORCH=cpu -t iid-sinhala-asr-cpu services/sinhala-asr`, then run it with `-e OMNIASR_MODEL_CARD=omniASR_CTC_1B_v2`. For a Space, see [`deploy/huggingface`](../../deploy/huggingface/README.md) |
| Locally | `pip install omnilingual-asr==0.2.0 pyarrow==22.0.0 "fastapi[standard]"`, then `uvicorn server:app --port 9000` |

Then set these on the If I Disappear server:

```
SINHALA_ASR_URL=https://<your service>
SINHALA_ASR_TOKEN=<the same token>
```

The model downloads and loads when the service starts; `GET /health` says which model it is and
whether it is ready. Set `OMNIASR_PRELOAD=0` to load it on the first request instead. The tests
(`python -m pytest -q services/sinhala-asr`) check the contract with the backend, with a stand-in
for the model.
