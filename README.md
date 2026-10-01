# ig-reel

Free Instagram reel generator + publisher (official Graph API).

- **Generate**: topic → AI script (via any OpenAI-compatible endpoint, e.g. [modelgate](https://github.com/fiyasis/modelgate)) → Hindi/English TTS → animated 9:16 video with captions, 26–40s
- **Publish**: official Instagram Graph API (Business/Creator account) — no BAN risk
- **Cost**: $0 (free LLM via modelgate + edge-tts + local ffmpeg)

## Setup

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

`imageio-ffmpeg` brings a static ffmpeg binary — no system install needed.
Hindi captions need Devanagari fonts (already present on most Linux distros:
`NotoSansDevanagari`); otherwise install `fonts-noto-core`.

## 1. Generate a reel

```sh
# topic -> full pipeline (needs a running modelgate / any OpenAI endpoint)
.venv/bin/python reel_gen.py --topic "3 AI tools har developer ko free me" \
  --modelgate http://127.0.0.1:8787 --model fast \
  --handle @yourhandle --out reel.mp4

# or bring your own script (one line per segment, # = comment)
.venv/bin/python reel_gen.py --script myscript.txt --voice hi-IN-SwaraNeural --out reel.mp4

# add background music (royalty-free mp3)
.venv/bin/python reel_gen.py --topic "..." --music music.mp3 --music-volume 0.15 --out reel.mp4
```

Options: `--segments N` (default 6), `--voice` (any edge-tts voice, auto-picks
`hi-IN-SwaraNeural` when the script contains Devanagari).
Output: `reel.mp4` (1080x1920, H.264 + AAC — Instagram-compatible) and
`reel_caption.txt` with a ready caption + hashtags.

## 2. Publish (official Graph API)

Prereqs: Instagram account switched to **Professional (Business or Creator)**,
a linked Facebook Page, and a Meta developer app with permissions
`instagram_content_publish`, `pages_show_list`, `pages_manage_metadata`.
Use a **long-lived user token** (not the page token). Get the token from Meta
Graph Explorer (user token, ~60 days — refreshable) or your app's OAuth flow.

```sh
# one-shot: upload + wait + publish
.venv/bin/python ig_publish.py --page-id 1234567890 --token USTOKEN \
  --video reel.mp4 --caption "see caption.txt"

# if the container takes longer than the request window, retry with its id
.venv/bin/python ig_publish.py --page-id 1234567890 --token USTOKEN --container <id>
```

The tool prints the live reel URL on success.

## Why not the unofficial route?

Session-cookie scrapers (`instagrapi`) work on personal accounts but are a
Terms-of-Service violation with real account-limit/BAN risk. The official API
is free and safe — it only needs a Business/Creator account, which takes
30 seconds to switch to in the Instagram app.

## License

MIT
