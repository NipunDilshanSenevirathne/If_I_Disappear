# Sinhala speech (Meta's Omnilingual ASR) as a small web service.
#
# On a GPU host, with the default model (omniASR_LLM_1B_v2):
#   docker build -t iid-sinhala-asr services/sinhala-asr
#   docker run --gpus all -p 9000:9000 -e SINHALA_ASR_TOKEN=... iid-sinhala-asr
#
# On a CPU host (a smaller image, and a CTC model, which was measured on CPU; see README.md):
#   docker build --build-arg TORCH=cpu -t iid-sinhala-asr-cpu services/sinhala-asr
#   docker run -p 9000:9000 -e OMNIASR_MODEL_CARD=omniASR_CTC_1B_v2 -e SINHALA_ASR_TOKEN=... iid-sinhala-asr-cpu
FROM python:3.11-slim
ARG TORCH=cuda
# A C++ toolchain, because one dependency (kenlm) has no wheel and is compiled on install:
# without it, a plain build of this image failed (28 October 2026).
RUN apt-get update && apt-get install -y --no-install-recommends libsndfile1 ffmpeg build-essential cmake zlib1g-dev libbz2-dev liblzma-dev && rm -rf /var/lib/apt/lists/* \
 && useradd --create-home --uid 1000 asr && mkdir -p /cache && chown asr /cache
# fairseq2 0.6 is built against PyTorch 2.8.0. Its CPU build comes from Meta's own package index.
RUN if [ "$TORCH" = "cpu" ]; then \
      pip install --no-cache-dir torch==2.8.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cpu \
      && pip install --no-cache-dir "fairseq2n==0.6+cpu" --extra-index-url https://fair.pkg.atmeta.com/fairseq2/whl/pt2.8.0/cpu; \
    fi
# pyarrow is pinned because fairseq2 needs NumPy 1.x: a plain install picked pyarrow 26, which
# needs NumPy 2 and failed when the model loaded (28 October 2026). pyarrow 22 works.
RUN pip install --no-cache-dir omnilingual-asr==0.2.0 pyarrow==22.0.0 "fastapi[standard]==0.115.12"
WORKDIR /srv
COPY server.py .
ENV FAIRSEQ2_CACHE_DIR=/cache XDG_CACHE_HOME=/cache PORT=9000
USER asr
EXPOSE 9000
CMD ["sh", "-c", "exec uvicorn server:app --host 0.0.0.0 --port ${PORT}"]
