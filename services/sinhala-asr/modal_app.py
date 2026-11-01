"""Run the Sinhala speech service on Modal with a GPU.

    pip install modal
    modal secret create iid-sinhala-asr SINHALA_ASR_TOKEN=<a long random string>
    modal deploy services/sinhala-asr/modal_app.py

Then set SINHALA_ASR_URL (the printed URL) and SINHALA_ASR_TOKEN on the If I Disappear server.
"""

from pathlib import Path

import modal

HERE = Path(__file__).resolve().parent
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("libsndfile1", "ffmpeg", "build-essential", "cmake", "zlib1g-dev", "libbz2-dev", "liblzma-dev")  # kenlm compiles on install
    .pip_install("omnilingual-asr==0.2.0", "pyarrow==22.0.0", "fastapi[standard]==0.115.12")  # pyarrow: see Dockerfile
    .env({"XDG_CACHE_HOME": "/cache", "FAIRSEQ2_CACHE_DIR": "/cache/fairseq2", "OMNIASR_PRELOAD": "0"})  # load() below loads it
    .add_local_file(HERE / "server.py", "/root/server.py")
)
app = modal.App("iid-sinhala-asr", image=image)
cache = modal.Volume.from_name("iid-omniasr-cache", create_if_missing=True)


@app.cls(gpu="L4", scaledown_window=300, timeout=900, volumes={"/cache": cache}, secrets=[modal.Secret.from_name("iid-sinhala-asr")])
class SinhalaASR:
    @modal.enter()
    def load(self):
        from omnilingual_asr.models.inference.pipeline import ASRInferencePipeline

        import server

        self.app = server.create_app(ASRInferencePipeline(model_card=server.MODEL_CARD))
        cache.commit()

    @modal.asgi_app()
    def web(self):
        return self.app
