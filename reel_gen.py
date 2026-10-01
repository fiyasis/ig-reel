#!/usr/bin/env python3
import argparse
import asyncio
import json
import math
import os
import re
import subprocess
import sys
import urllib.request

import imageio_ffmpeg
import edge_tts
from PIL import Image, ImageDraw, ImageFont

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
W, H = 1080, 1920
DEVA = re.compile(r"[\u0900-\u097F]")
FONT_LATIN = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_LATIN_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_DEVA = "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf"
FONT_DEVA_REG = "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf"
PALETTES = [
    ((15, 15, 25), (60, 40, 120)),
    ((10, 25, 35), (0, 90, 110)),
    ((30, 12, 40), (120, 40, 90)),
    ((25, 20, 10), (110, 80, 20)),
    ((12, 28, 22), (30, 110, 80)),
]


def http_post_json(url, payload, timeout=120):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def gen_script(modelgate, model, topic, n=6):
    prompt = (
        f"Write a {n}-segment Instagram reel script about: {topic}\n"
        "Rules: write in the SAME language as the topic (if the topic is Hinglish/Hindi, write the script in Hinglish/Hindi). "
        "Hook first, punchy short lines, each segment 6-16 words, "
        "last segment ends with a call to action. Output EXACTLY this format, nothing else:\n"
        "SEG 1: ...\nSEG 2: ..."
    )
    data = http_post_json(
        f"{modelgate.rstrip('/')}/v1/chat/completions",
        {"model": model, "max_tokens": 700,
         "messages": [{"role": "user", "content": prompt}]},
    )
    text = data["choices"][0]["message"]["content"]
    segs = re.findall(r"SEG\s+\d+\s*:\s*(.+)", text, re.IGNORECASE)
    if not segs:
        segs = [ln.strip() for ln in text.splitlines() if ln.strip() and "SEG" not in ln]
    if not segs:
        raise RuntimeError("script generation returned no segments: " + text[:200])
    return [s.strip() for s in segs]


def split_words(text, max_words=30):
    words = text.split()
    out, cur = [], []
    for w in words:
        cur.append(w)
        if len(cur) >= max_words:
            out.append(" ".join(cur))
            cur = []
    if cur:
        out.append(" ".join(cur))
    return out


def audio_dur(path):
    r = subprocess.run([FFMPEG, "-i", path], capture_output=True, text=True)
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", r.stderr)
    if not m:
        raise RuntimeError("could not read duration: " + r.stderr[:200])
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


def tts(text, voice, out):
    async def _run():
        await edge_tts.Communicate(text, voice).save(out)
    asyncio.run(_run())


def pick_font(devanagari, size):
    bold = FONT_DEVA if devanagari else FONT_LATIN
    reg = FONT_DEVA_REG if devanagari else FONT_LATIN_REG
    return ImageFont.truetype(bold, size), ImageFont.truetype(reg, size)


def gradient(c1, c2, y):
    t = y / H
    return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))


def wrap(draw, text, font, max_w):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if draw.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def draw_slide(text, topic, idx, out, handle=""):
    pal = PALETTES[idx % len(PALETTES)]
    img = Image.new("RGB", (W, H))
    px = img.load()
    for y in range(H):
        c = gradient(pal[0], pal[1], y)
        for x in range(W):
            px[x, y] = c
    d = ImageDraw.Draw(img)
    deva = bool(DEVA.search(text))
    f_big, f_small = pick_font(deva, 78)
    f_topic, _ = pick_font(bool(DEVA.search(topic)), 40)
    f_brand, _ = pick_font(False, 34)
    if topic:
        tw = d.textlength(topic.upper(), font=f_topic)
        d.text(((W - tw) / 2, 220), topic.upper(), font=f_topic, fill=(255, 255, 255, 200))
    d.text(((W - d.textlength(f"{idx+1}", font=f_topic)) / 2, 290), f"{idx+1}", font=f_topic, fill=(255, 210, 100))
    lines = wrap(d, text, f_big, W - 160)
    if len(lines) > 5:
        f_big, _ = pick_font(deva, 62)
        lines = wrap(d, text, f_big, W - 160)
    lh = 104 if f_big.size > 70 else 84
    total_h = lh * len(lines)
    y0 = (H - total_h) / 2
    for i, ln in enumerate(lines):
        lw = d.textlength(ln, font=f_big)
        x = (W - lw) / 2
        y = y0 + i * lh
        d.text((x + 5, y + 5), ln, font=f_big, fill=(0, 0, 0))
        d.text((x, y), ln, font=f_big, fill=(255, 255, 255))
    if handle:
        hw = d.textlength(handle, font=f_brand)
        d.text(((W - hw) / 2, H - 140), handle, font=f_brand, fill=(255, 255, 255, 160))
    img.save(out)


def make_clip(slide, audio, dur, out):
    cmd = [
        FFMPEG, "-y", "-loop", "1", "-framerate", "30", "-t", f"{dur:.3f}", "-i", slide,
        "-i", audio,
        "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,format=yuv420p",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k", "-r", "30",
        "-movflags", "+faststart", out,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg clip failed: " + r.stderr[-800:])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--topic")
    ap.add_argument("--script")
    ap.add_argument("--voice")
    ap.add_argument("--modelgate", default=os.environ.get("MODELGATE_URL", "http://127.0.0.1:8787"))
    ap.add_argument("--model", default="fast")
    ap.add_argument("--music")
    ap.add_argument("--music-volume", type=float, default=0.15)
    ap.add_argument("--handle", default="")
    ap.add_argument("--segments", type=int, default=6)
    ap.add_argument("--out", default="reel.mp4")
    a = ap.parse_args()

    if not a.topic and not a.script:
        ap.error("need --topic or --script")

    work = a.out + ".work"
    os.makedirs(work, exist_ok=True)

    if a.script:
        with open(a.script, encoding="utf-8") as f:
            segs = [ln.strip() for ln in f if ln.strip() and not ln.strip().startswith("#")]
        topic = " ".join(segs[:1])[:60]
    else:
        topic = a.topic
        print(f"[reel] generating script via {a.modelgate} (model: {a.model}) ...")
        segs = gen_script(a.modelgate, a.model, topic, a.segments)
        print(f"[reel] script segments: {len(segs)}")

    for i, s in enumerate(segs):
        while len(s.split()) > 30:
            parts = split_words(s, 22)
            segs[i:i + 1] = parts
            s = parts[0]
    segs = segs[:12]

    sample = " ".join(segs)
    voice = a.voice or ("hi-IN-SwaraNeural" if DEVA.search(sample) else "en-US-GuyNeural")
    print(f"[reel] voice: {voice}, segments: {len(segs)}")

    listf = os.path.join(work, "concat.txt")
    with open(listf, "w") as f:
        for i, s in enumerate(segs):
            slide = os.path.join(work, f"slide_{i:02d}.png")
            aud = os.path.join(work, f"seg_{i:02d}.mp3")
            clip = os.path.join(work, f"clip_{i:02d}.mp4")
            print(f"[reel] segment {i+1}/{len(segs)}: {s[:60]}...")
            draw_slide(s, topic, i, slide, a.handle)
            tts(s, voice, aud)
            dur = audio_dur(aud)
            dur = max(2.2, min(dur + 0.35, 15.0))
            make_clip(slide, aud, dur, clip)
            f.write(f"file '{clip}'\n")

    raw = os.path.join(work, "reel_raw.mp4")
    r = subprocess.run(
        [FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", listf, "-c", "copy", raw],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise RuntimeError("concat failed: " + r.stderr[-500:])

    total = audio_dur(raw)
    if a.music and os.path.exists(a.music):
        r = subprocess.run(
            [FFMPEG, "-y", "-i", raw, "-stream_loop", "-1", "-i", a.music,
             "-filter_complex", f"[1:a]volume={a.music_volume}[m];[0:a][m]amix=inputs=2:duration=first:dropout_transition=2[a]",
             "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
             "-movflags", "+faststart", a.out],
            capture_output=True, text=True,
        )
        if r.returncode != 0:
            raise RuntimeError("music mix failed: " + r.stderr[-500:])
    else:
        import shutil
        shutil.move(raw, a.out)

    cap_path = os.path.splitext(a.out)[0] + "_caption.txt"
    with open(cap_path, "w", encoding="utf-8") as f:
        f.write(topic + "\n\n" + " ".join(segs) + "\n\n#reels #instadaily #foryoupage\n")

    print(f"[reel] DONE -> {a.out} ({total:.1f}s)")
    print(f"[reel] caption -> {cap_path}")


if __name__ == "__main__":
    main()
