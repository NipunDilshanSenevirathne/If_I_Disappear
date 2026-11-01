---
title: If I Disappear Sinhala speech
emoji: 🗣️
colorFrom: yellow
colorTo: gray
sdk: docker
app_port: 9000
pinned: false
license: apache-2.0
short_description: Sinhala speech to text with Meta's Omnilingual ASR
---

# Sinhala speech for If I Disappear

Meta's open-source Omnilingual ASR (`omniASR_CTC_1B_v2`, on CPU) as a small service for
If I Disappear's Sinhala walk-throughs. `POST /transcribe` needs the Space's `SINHALA_ASR_TOKEN`;
`GET /health` says whether the model is loaded.

Measured on 189 public Sinhala recordings (OpenSLR SLR30): 12.4% character error rate, 3.2 times
faster than real time on 2 CPUs. Details in the project's `services/sinhala-asr/README.md`.
