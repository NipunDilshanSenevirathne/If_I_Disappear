#!/usr/bin/env python3
"""The synthetic walk-through that frontend/tests/live_full.cjs records through the web app.

    python scripts/make_test_walkthrough.py OUT_DIR [en|si]

Writes OUT_DIR/walk-<lang>.mp4 and OUT_DIR/walk-<lang>.json (each room's start and end, each line
said). Needs ffmpeg, espeak-ng and Pillow. Nothing here is a real home or a real person:

- the voice is eSpeak NG's (en-gb, or its Sinhala voice);
- the main switch, the pump, the cupboard and the room photos are the app's own sample photos;
- the cupboard has a made-up bank card on its shelf ("SAMPLE TEST BANK", the public test number
  4111 1111 1111 1111, a made-up name), drawn here, which the camera pans onto, so the privacy
  pass has something real to find;
- the padlock (468867) and the clock (14298) are photographs by The Metropolitan Museum of Art,
  Open Access, CC0, from evals/heldout/photos, so another photograph of the same object can be the
  family member's "show me" photo (14298-2: the same clock from the front, in other light, the
  pair the app confirmed in all three runs of the held-out photos);
- one line says a gate code aloud and one says a medicine instruction: neither may be kept.

The rooms, in order: the main switch box, the water pump, the papers in the bedroom cupboard (the
pan onto the card), the padlock on the back gate, the clock in the hall, and a room where the code
and the medicine are said.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import wave
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / "backend" / "fixtures" / "base"
HELD = ROOT / "evals" / "heldout" / "photos"
WALL = "0xdad9d5"  # a museum photo is shown whole, against a plain wall, not cropped

SCRIPT = {
    "en": [
        ("breaker", BASE / "breaker.jpg", "zoom", [
            "This is the main switch box, next to the kitchen door.",
            "If the power goes off, come here first.",
            "Find the switch that has dropped down, and push it back up.",
            "Never touch it with wet hands.",
        ]),
        ("pump", BASE / "pump.jpg", "zoom", [
            "This is the water pump, behind the house.",
            "Every morning at six, switch it on for twenty minutes, until the tank is full.",
            "Do not run it at night.",
        ]),
        ("documents", None, "pan", [
            "These white files in the bedroom cupboard hold the house deed and the birth certificates.",
            "Never give the originals to anyone. Give photocopies instead.",
        ]),
        ("padlock", HELD / "met-468867-0.jpg", "zoom", [
            "This is the padlock on the back gate.",
            "Lock it every night. The key hangs on the hook inside the kitchen door.",
        ]),
        ("clock", HELD / "met-14298-0.jpg", "zoom", [
            "This is the clock in the hall.",
            "Wind it every Sunday morning. Never turn the hands backwards.",
        ]),
        ("interior", BASE / "interior.jpg", "zoom", [
            "The gate code is two five eight zero.",
            "Amma takes her pressure pill at eight every night.",
        ]),
    ],
    "si": [
        ("breaker", BASE / "breaker.jpg", "zoom", [
            "මේ තියෙන්නේ ප්‍රධාන ස්විච් පෙට්ටිය, කුස්සියේ දොර ළඟ.",
            "කරන්ට් ගියොත් මුලින්ම මෙතනට එන්න.",
            "පහළට වැටිලා තියෙන ස්විච් එක හොයාගෙන, ඒක ආපහු උඩට දාන්න.",
            "තෙත අත්වලින් කවදාවත් අල්ලන්න එපා.",
        ]),
        ("pump", BASE / "pump.jpg", "zoom", [
            "මේ තියෙන්නේ වතුර මෝටරය, ගෙදර පිටිපස්සේ.",
            "හැමදාම උදේ හයට, ටැංකිය පිරෙනකම් විනාඩි විස්සක් මෝටරය දාන්න.",
            "රෑට මෝටරය දාන්න එපා.",
        ]),
        ("documents", None, "pan", [
            "නිදන කාමරේ අල්මාරියේ තියෙන මේ සුදු ෆයිල්වල ගෙදර ඔප්පුවයි උප්පැන්න සහතිකයි තියෙනවා.",
            "මුල් පිටපත් කාටවත් දෙන්න එපා. ෆොටෝ කොපි දෙන්න.",
        ]),
        ("padlock", HELD / "met-468867-0.jpg", "zoom", [
            "මේ තියෙන්නේ පිටිපස්සේ ගේට්ටුවේ ඉබ්බා.",
            "හැමදාම රෑට ඒක ලොක් කරන්න. යතුර එල්ලලා තියෙන්නේ කුස්සියේ දොර ඇතුළේ කොක්කේ.",
        ]),
        ("clock", HELD / "met-14298-0.jpg", "zoom", [
            "මේ තියෙන්නේ සාලේ ඔරලෝසුව.",
            "හැම ඉරිදාම උදේ ඒකට කී දෙන්න. කටු කවදාවත් පස්සට කරකවන්න එපා.",
        ]),
        ("interior", BASE / "interior.jpg", "zoom", [
            "ගේට්ටුවේ කෝඩ් එක දෙක පහ අට බිංදුව.",
            "අම්මා හැමදාම රෑ අටට ප්‍රෙෂර් පෙත්ත බොනවා.",
        ]),
    ],
}


def _font(names: list[str], size: int):
    for name in names:
        for folder in ("/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/dejavu", "/Library/Fonts", "C:/Windows/Fonts"):
            p = Path(folder) / name
            if p.exists():
                return ImageFont.truetype(str(p), size)
    return ImageFont.load_default()


def card(w: int = 430, h: int = 271) -> Image.Image:
    """A made-up bank card: no brand, the public test number, a made-up name."""
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    grad = Image.new("RGB", (w, h))
    px = grad.load()
    for x in range(w):
        for y in range(h):
            t = (x + y) / (w + h)
            px[x, y] = (int(20 + 30 * t), int(40 + 60 * t), int(110 + 90 * t))
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius=22, fill=255)
    im.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((40, 85, 100, 130), radius=8, fill=(212, 175, 55), outline=(150, 120, 30), width=2)  # the chip
    for i in range(3):
        d.line((40, 100 + i * 10, 100, 100 + i * 10), fill=(150, 120, 30), width=1)
    mono, sans = ["DejaVuSansMono-Bold.ttf"], ["DejaVuSans-Bold.ttf"]
    d.text((40, 28), "SAMPLE TEST BANK", font=_font(sans, 22), fill=(255, 255, 255))
    d.text((40, 150), "4111 1111 1111 1111", font=_font(mono, 30), fill=(240, 240, 240))
    d.text((40, 200), "VALID THRU 12/29", font=_font(mono, 16), fill=(220, 220, 220))
    d.text((40, 225), "A PERERA", font=_font(mono, 20), fill=(240, 240, 240))
    for r in (12, 22, 32):  # a plain contactless mark, no brand
        d.arc((w - 70 - r, h - 60 - r, w - 70 + r, h - 60 + r), start=-50, end=50, fill=(230, 230, 230), width=4)
    return im


def card_scene(out: Path) -> Path:
    """The sample's cupboard photo with the card lying on the shelf, to the right."""
    base = Image.open(BASE / "documents.jpg").convert("RGB")
    c = card().rotate(-8, expand=True, resample=Image.BICUBIC)
    shadow = Image.new("RGBA", c.size, (0, 0, 0, 0))
    shadow.paste((0, 0, 0, 120), (0, 0), c.split()[3])
    shadow = shadow.filter(ImageFilter.GaussianBlur(8))
    x, y = 1180, 620
    base.paste(shadow, (x + 10, y + 12), shadow)
    base.paste(c, (x, y), c)
    path = out / "card-scene.jpg"
    base.save(path, quality=92)
    return path


def main(out: Path, lang: str) -> None:
    for tool in ("ffmpeg", "espeak-ng"):
        if not shutil.which(tool):
            raise SystemExit(f"This needs {tool} on the PATH.")
    out.mkdir(parents=True, exist_ok=True)
    scene = card_scene(out)
    rate, pcm, rooms, lines_at = 22050, bytearray(), [], []

    def silence(seconds: float) -> None:
        pcm.extend(b"\x00\x00" * int(rate * seconds))

    silence(0.8)
    n = 0
    for room, photo, move, lines in SCRIPT[lang]:
        photo = photo or scene
        start = len(pcm) / 2 / rate
        for line in lines:
            wav = out / f"{lang}-line{n:02d}.wav"
            n += 1
            subprocess.run(["espeak-ng", "-v", "si" if lang == "si" else "en-gb", "-s", "130" if lang == "si" else "140", "-w", str(wav), line], check=True)
            with wave.open(str(wav)) as w:
                if (w.getframerate(), w.getsampwidth(), w.getnchannels()) != (rate, 2, 1):
                    raise SystemExit("espeak-ng wrote an unexpected WAV format")
                at = len(pcm) / 2 / rate
                pcm.extend(w.readframes(w.getnframes()))
                lines_at.append({"line": line, "start": round(at, 2), "end": round(len(pcm) / 2 / rate, 2)})
            wav.unlink()
            silence(0.7)
        silence(0.5)
        rooms.append({"room": room, "photo": str(photo.relative_to(ROOT) if photo.is_relative_to(ROOT) else photo.name), "move": move,
                      "start": round(start, 2), "end": round(len(pcm) / 2 / rate, 2), "_path": photo})
    rooms[0]["start"] = 0.0
    speech = out / f"speech-{lang}.wav"
    with wave.open(str(speech), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(pcm))

    cmd = ["ffmpeg", "-y", "-loglevel", "error"]
    for r in rooms:
        if r["move"] == "pan":
            cmd += ["-loop", "1", "-t", f"{r['end'] - r['start']:.2f}", "-i", str(r["_path"])]
        else:  # zoompan makes all its frames from one picture
            cmd += ["-i", str(r["_path"])]
    cmd += ["-i", str(speech)]
    parts = []
    for i, r in enumerate(rooms):
        seconds = r["end"] - r["start"]
        frames = int(seconds * 25) + 1
        if r["move"] == "pan":  # from the left of the cupboard to the right, where the card is
            parts.append(f"[{i}:v]scale=1920:1080,crop=1280:720:'(iw-1280)*t/{max(1.0, seconds):.2f}':180,setsar=1,fps=25,format=yuv420p[v{i}]")
            continue
        w, h = Image.open(r["_path"]).size
        # A museum photo (tall or square) is shown whole against a plain wall, not cropped to the
        # frame, so the object stays in view the whole time it is talked about.
        museum = r["_path"].parent == HELD
        fit = (f"scale=1600:900:force_original_aspect_ratio=decrease,pad=1600:900:(ow-iw)/2:(oh-ih)/2:color={WALL}" if museum or h > w
               else "scale=1600:900:force_original_aspect_ratio=increase,crop=1600:900")
        # A slow push in towards the middle, as a phone held on the thing being explained.
        parts.append(f"[{i}:v]{fit},zoompan=z='min(zoom+0.0006,1.12)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s=1280x720:fps=25,setsar=1,format=yuv420p[v{i}]")
    graph = ";".join(parts) + ";" + "".join(f"[v{i}]" for i in range(len(rooms))) + f"concat=n={len(rooms)}:v=1:a=0[v]"
    video = out / f"walk-{lang}.mp4"
    cmd += ["-filter_complex", graph, "-map", "[v]", "-map", f"{len(rooms)}:a", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", str(video)]
    subprocess.run(cmd, check=True)
    speech.unlink()
    for r in rooms:
        r.pop("_path")
    voice = "eSpeak NG (si)" if lang == "si" else "eSpeak NG (en-gb)"
    (out / f"walk-{lang}.json").write_text(json.dumps({"voice": voice, "rooms": rooms, "lines": lines_at}, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{video}  {rooms[-1]['end']} s, {len(rooms)} rooms, {len(lines_at)} lines")


if __name__ == "__main__":
    if len(sys.argv) < 2 or (len(sys.argv) > 2 and sys.argv[2] not in SCRIPT):
        raise SystemExit(__doc__)
    main(Path(sys.argv[1]).resolve(), sys.argv[2] if len(sys.argv) > 2 else "en")
