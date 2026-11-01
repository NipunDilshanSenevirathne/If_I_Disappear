#!/usr/bin/env python3
"""Put If I Disappear on Hugging Face Spaces: the app, and Sinhala speech beside it.
Docker Spaces need a PRO account (since mid-2026 Hugging Face refuses them on a free account with
HTTP 402); they run on the basic CPU, 2 vCPUs and 16 GB.

    pip install huggingface_hub
    export HF_TOKEN=hf_...                                  # a token with write access
    python deploy/huggingface/push.py app     <you>/if-i-disappear
    python deploy/huggingface/push.py sinhala <you>/iid-sinhala-asr --link <you>/if-i-disappear
    python deploy/huggingface/push.py app     <you>/if-i-disappear --dry-run   # only assemble the folder

`app` makes a public Docker Space running the app on the basic CPU (2 vCPUs, 16 GB): the sample
home works at once, with no key. For real recordings, pass --live with MODEL_API_KEY set in your
environment: it becomes a secret on the Space, never a file in it. --live also makes the invite
code for the Start page (IID_ADMIN_TOKEN) and the key that signs links (IID_LINK_SECRET) if you
haven't set them, sets a lifetime spending cap of $25 unless IID_TOTAL_BUDGET_USD says otherwise,
and prints the invite code once, for you to keep.

    MODEL_API_KEY=... python deploy/huggingface/push.py app <you>/if-i-disappear --live

`sinhala` makes a second Docker Space for Sinhala speech: Omnilingual ASR's 1B CTC model on CPU,
the model measured in services/sinhala-asr/README.md. It makes a random token, keeps it as a
secret on that Space, and with --link also sets SINHALA_ASR_URL and SINHALA_ASR_TOKEN on the app's
Space, so the two are joined. Nothing secret is printed.

Spaces on the basic CPU sleep after two days without visitors and wake on the next visit (a minute or two).
Their disk is wiped on restart, which suits the sample home; real homes need paid storage or a
host with a disk (deploy/cloud-run.sh).
"""

from __future__ import annotations

import argparse
import os
import re
import secrets
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent

APP_FILES = ["Dockerfile", ".dockerignore", "backend/requirements.txt", "backend/app", "backend/fixtures/sample", "frontend", "LICENSE", "NOTICE"]
SKIP = re.compile(r"(^|/)(node_modules|__pycache__|\.pytest_cache|tests/__pycache__)(/|$)|\.pyc$")
LIVE_SECRETS = ["MODEL_API_KEY", "IID_ADMIN_TOKEN", "IID_LINK_SECRET", "SINHALA_ASR_URL", "SINHALA_ASR_TOKEN",
                "WHATSAPP_TOKEN", "WHATSAPP_PHONE_NUMBER_ID", "WHATSAPP_VERIFY_TOKEN", "WHATSAPP_APP_SECRET"]
LIVE_VARIABLES = ["IID_MODE", "IID_DAILY_BUDGET_USD", "IID_TOTAL_BUDGET_USD", "IID_ALLOW_PUBLIC_LIVE", "IID_PUBLIC_BASE_URL", "IID_MAX_UPLOAD_MB"]


def copy(src: Path, dst: Path) -> None:
    if src.is_dir():
        for p in sorted(src.rglob("*")):
            rel = p.relative_to(ROOT).as_posix()
            if p.is_file() and not SKIP.search(rel):
                (dst / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, dst / rel)
    else:
        rel = src.relative_to(ROOT).as_posix()
        (dst / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst / rel)


def assemble_app(out: Path) -> None:
    for name in APP_FILES:
        copy(ROOT / name, out)
    # The .dockerignore leaves out what a Space doesn't need; keep the web app's own folder clean.
    shutil.copy2(HERE / "app-space.md", out / "README.md")


def assemble_sinhala(out: Path) -> None:
    src = ROOT / "services" / "sinhala-asr"
    shutil.copy2(src / "server.py", out / "server.py")
    dockerfile = (src / "Dockerfile").read_text(encoding="utf-8")
    # A basic CPU Space has no GPU: build the CPU image, with the CPU-measured model.
    dockerfile = dockerfile.replace("ARG TORCH=cuda", "ARG TORCH=cpu", 1)
    dockerfile = dockerfile.replace("ENV FAIRSEQ2_CACHE_DIR=/cache XDG_CACHE_HOME=/cache PORT=9000",
                                    "ENV FAIRSEQ2_CACHE_DIR=/cache XDG_CACHE_HOME=/cache PORT=9000 OMNIASR_MODEL_CARD=omniASR_CTC_1B_v2", 1)
    if "ARG TORCH=cpu" not in dockerfile or "omniASR_CTC_1B_v2" not in dockerfile:
        raise SystemExit("services/sinhala-asr/Dockerfile changed; update deploy/huggingface/push.py to match.")
    (out / "Dockerfile").write_text(dockerfile, encoding="utf-8")
    shutil.copy2(HERE / "sinhala-space.md", out / "README.md")


def space_host(api, repo_id: str) -> str:
    info = api.space_info(repo_id)
    host = getattr(info, "host", None)
    if host:
        return host.rstrip("/")
    owner, name = repo_id.split("/", 1)
    return "https://" + re.sub(r"[^a-z0-9-]", "-", f"{owner}-{name}".lower()) + ".hf.space"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=["app", "sinhala"])
    ap.add_argument("space", help="<owner>/<name> of the Space to create or update")
    ap.add_argument("--link", help="for sinhala: the app's Space, to set SINHALA_ASR_URL and SINHALA_ASR_TOKEN on it")
    ap.add_argument("--live", action="store_true", help="for app: copy the live settings and secrets in LIVE_SECRETS from your environment")
    ap.add_argument("--private", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="only assemble the folder, and print where it is")
    args = ap.parse_args()
    invite = None
    if args.what == "app" and args.live:
        if not os.environ.get("MODEL_API_KEY"):
            raise SystemExit("--live needs MODEL_API_KEY in your environment (it is sent as a secret, never written to a file).")
        if not os.environ.get("IID_ADMIN_TOKEN"):
            invite = os.environ["IID_ADMIN_TOKEN"] = secrets.token_urlsafe(12)
        os.environ.setdefault("IID_LINK_SECRET", secrets.token_urlsafe(32))
        os.environ.setdefault("IID_TOTAL_BUDGET_USD", "25")

    out = Path(tempfile.mkdtemp(prefix=f"iid-space-{args.what}-"))
    (assemble_app if args.what == "app" else assemble_sinhala)(out)
    files = sum(1 for p in out.rglob("*") if p.is_file())
    if args.dry_run:
        print(f"Assembled {files} files in {out}")
        return

    try:
        from huggingface_hub import HfApi
    except ImportError:
        raise SystemExit("pip install huggingface_hub")
    if not os.environ.get("HF_TOKEN"):
        raise SystemExit("Set HF_TOKEN to a Hugging Face token with write access.")
    api = HfApi()
    api.create_repo(args.space, repo_type="space", space_sdk="docker", private=args.private, exist_ok=True)

    if args.what == "app":
        # The Space page shows the app in a frame; only that page may frame it.
        api.add_space_variable(args.space, "IID_FRAME_ANCESTORS", "https://huggingface.co")
        if args.live:
            for key in LIVE_SECRETS:
                if os.environ.get(key):
                    api.add_space_secret(args.space, key, os.environ[key])
            for key in LIVE_VARIABLES:
                if os.environ.get(key):
                    api.add_space_variable(args.space, key, os.environ[key])
    else:
        token = secrets.token_urlsafe(32)
        api.add_space_secret(args.space, "SINHALA_ASR_TOKEN", token)
        if args.link:
            api.add_space_secret(args.link, "SINHALA_ASR_TOKEN", token)
            api.add_space_secret(args.link, "SINHALA_ASR_URL", space_host(api, args.space))

    api.upload_folder(repo_id=args.space, repo_type="space", folder_path=out, commit_message=f"If I Disappear: {args.what}")
    shutil.rmtree(out, ignore_errors=True)
    print(f"Pushed {files} files. Building now; it opens at {space_host(api, args.space)}")
    if args.what == "app" and args.live:
        print(f"Real homes start at {space_host(api, args.space)}/start")
        print(f"Spending caps: ${os.environ.get('IID_DAILY_BUDGET_USD', '5')} a day, ${os.environ['IID_TOTAL_BUDGET_USD']} in all (counted since the Space last started).")
        if invite:
            print(f"Invite code for the Start page: {invite}")
            print("Keep it somewhere safe: it isn't shown again. It is also a secret on the Space (IID_ADMIN_TOKEN).")
    if args.what == "sinhala":
        print("The first start downloads the 3.9 GB model, so give it a few minutes; /health says when it is ready.")
        if args.link:
            print(f"{args.link} now has SINHALA_ASR_URL and SINHALA_ASR_TOKEN; restart it from its settings page.")


if __name__ == "__main__":
    sys.exit(main())
