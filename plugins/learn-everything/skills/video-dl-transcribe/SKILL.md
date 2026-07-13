---
name: video-dl-transcribe
description: >
  Fetch a transcript from any video URL or local file. Tries platform subtitles first;
  falls back to Whisper speech recognition (GPU-accelerated on Apple Silicon) if unavailable.
allowed-tools: Bash Read
argument-hint: <url-or-file> [--lang LANG] [--whisper-model large-v3|medium|small] [--cookies PATH] [--output PATH]
effort: medium
---

Input: $ARGUMENTS

## Paths

| Resource | Path |
|---|---|
| Python (venv) | `~/.claude/my-venvs/video-learn/bin/python` |
| Transcript script | `${CLAUDE_SKILL_DIR}/scripts/get_transcript.py` |
| Bilibili cookies | `~/.claude/my-auth/cookies-bilibili.txt` |
| Default output | `./tmp-claude/video-grab/{VIDEO_ID}/transcript.txt` |

## Step 0: Check deps

```bash
~/.claude/my-venvs/video-learn/bin/python -c "import yt_dlp; print('deps=ok')" 2>&1
command -v ffmpeg >/dev/null 2>&1 && echo "ffmpeg=ok" || echo "ffmpeg=missing"
```

If either check fails: tell user to run `learn-everything:video-dl-setup` skill first. Stop.

## Step 1: Parse arguments

- `SOURCE` — URL or local file path (required)
- `--lang LANG` — language hint (e.g. `en`, `zh`, `ja`)
- `--whisper-model MODEL` — model for speech recognition (default: `large-v3`). Only drop to a
  smaller model if the user asks for speed over accuracy.
- `--cookies PATH` — cookies file for sites requiring auth
- `--output PATH` — override default output path

The script picks the backend itself: `mlx-whisper` (Metal GPU) on Apple Silicon, `faster-whisper`
(CPU) elsewhere. Force one with `--backend mlx|faster` only when debugging.

## Step 0.5: Budget the runtime

Speech recognition is slow. Estimate before launching:

| Backend | Throughput (large-v3) | 60 min of audio |
|---|---|---|
| mlx-whisper (Apple Silicon GPU) | ~3x realtime | ~20 min |
| faster-whisper (CPU) | ~0.8x realtime | ~75 min |

For a local file longer than ~10 min, use `scripts/transcribe_chunked.py` instead of Step 2.
It splits with ffmpeg, transcribes chunk by chunk, offsets timestamps back onto the original
timeline, and caches each finished chunk — so no single command outlives its timeout
(`Bash` caps at 10 min, and background tasks may be reaped earlier), and an interrupted run
resumes for free.

```bash
~/.claude/my-venvs/video-learn/bin/python \
  "${CLAUDE_SKILL_DIR}/scripts/transcribe_chunked.py" \
  AUDIO --output OUTPUT_PATH --chunk-minutes 5 --workers 3 \
  [--lang LANG] [--model MODEL] [--max-chunks N]
```

It transcribes `--workers` chunks concurrently, which matters more than it looks: one Whisper
process leaves the GPU mostly idle, so 3 in parallel run several times faster than 1 (measured on
an M4: 1.7x realtime → 7.4x). Keep chunks small enough to parallelize (5 min is a good default) and
cap a pass with `--max-chunks` so it lands inside the timeout, then re-invoke the identical command
until it prints `ALL_CHUNKS_DONE`. Skip to Step 3 once it does.

For **dense continuous speech** (lectures), budget ~2x the throughput above; Whisper decodes token
by token, so a talky video is far slower than a sparse one of the same length. Measure one chunk
before promising the user a number.

If SOURCE is a Bilibili URL and `--cookies` not provided:
default to `~/.claude/my-auth/cookies-bilibili.txt`. If missing:
> ⚠ Bilibili requires cookies. Run the `learn-everything:video-dl-setup` skill for instructions.
Stop.

## Step 1.5: Fetch metadata (URLs only)

Skip if SOURCE is a local file path.

Invoke `learn-everything:video-dl-download` skill: `SOURCE --mode metadata [--cookies PATH]`

Print the result immediately.

## Step 2: Extract VIDEO_ID and fetch transcript

Extract VIDEO_ID from SOURCE:
- YouTube: parse `v=` param or last path segment of `youtu.be/` URL
- Bilibili: extract `BV[alphanumeric]+` from URL path
- Local file: filename without extension
- Fallback: `~/.claude/my-venvs/video-learn/bin/yt-dlp --get-id SOURCE`

Determine output path:
- If `--output PATH` given: use it
- Otherwise: `./tmp-claude/video-grab/{VIDEO_ID}/transcript.txt`

```bash
mkdir -p $(dirname OUTPUT_PATH)
~/.claude/my-venvs/video-learn/bin/python \
  "${CLAUDE_SKILL_DIR}/scripts/get_transcript.py" \
  SOURCE [--lang LANG] [--model WHISPER_MODEL] \
  [--cookies PATH] \
  --output OUTPUT_PATH
```

Read the saved file after the command completes. Parse header fields:
`SOURCE`, `QUALITY`, `WARN`, `TITLE`, `DURATION`

## Step 3: Report quality

Print:
```
Transcript: METHOD, lang=LANG, quality=QUALITY, DURATION min
VIDEO_ID: <id>
Path: OUTPUT_PATH
```

If METHOD contains `whisper`:
> ⚠ Used speech recognition (METHOD). Auto-generated — verify accuracy.

If WARN present: print it.
