---
name: video-dl-download
description: >
  yt-dlp wrapper. Downloads metadata, subtitles, audio, or full video from any URL.
  Supports YouTube and 1000+ sites. Bilibili requires cookies.
allowed-tools: Bash
argument-hint: <url> --mode metadata|subtitles|audio|video [--lang LANG] [--output PATH] [--cookies PATH]
effort: low
---

Input: $ARGUMENTS

## Paths

| Resource | Path |
|---|---|
| yt-dlp binary | `~/.claude/my-venvs/video-learn/bin/yt-dlp` |
| Bilibili cookies | `~/.claude/my-auth/cookies-bilibili.txt` |
| Default output dir | `./tmp-claude/video-grab/{VIDEO_ID}/` |

If `--cookies` not passed and SOURCE is a Bilibili URL, auto-use `~/.claude/my-auth/cookies-bilibili.txt` if it exists.

## Step 0: Check deps

```bash
[ -x ~/.claude/my-venvs/video-learn/bin/yt-dlp ] && echo "yt-dlp=ok" || echo "yt-dlp=missing — run the learn-everything:video-dl-setup skill first"
```

Stop if missing.

## Step 1: Parse arguments

- `URL` — video URL (required)
- `--mode MODE` — `metadata`, `subtitles`, `audio`, or `video` (required; error if missing)
- `--lang LANG` — language code for subtitles (e.g. `en`, `zh`, `ja`)
- `--output PATH` — output path override
- `--cookies PATH` — Netscape-format cookies file (required for Bilibili)

Default output paths when `--output` not given:
| Mode | Default |
|---|---|
| metadata | print to stdout only |
| subtitles | `./tmp-claude/video-grab/{VIDEO_ID}/` |
| audio | `./tmp-claude/video-grab/{VIDEO_ID}/audio.%(ext)s` |
| video | `./tmp-claude/video-grab/{VIDEO_ID}/video.%(ext)s` |

## Mode: metadata

```bash
~/.claude/my-venvs/video-learn/bin/yt-dlp \
  --print "TITLE:%(title)s\nUPLOADER:%(uploader)s\nDURATION:%(duration_string)s\nDESCRIPTION:%(description)s" \
  --no-download --no-playlist \
  [--cookies PATH] \
  "URL" 2>/dev/null || echo "METADATA_UNAVAILABLE"
```

## Mode: subtitles

```bash
~/.claude/my-venvs/video-learn/bin/yt-dlp \
  --write-auto-sub --write-sub \
  --sub-format vtt \
  --skip-download \
  --no-warnings --quiet \
  -o "OUTPUT_DIR/sub" \
  [--sub-lang LANG] \
  [--cookies PATH] \
  "URL"
```

List `*.vtt` files written. Print `NO_SUBTITLES` if none found.

## Mode: audio

```bash
~/.claude/my-venvs/video-learn/bin/yt-dlp \
  -x --audio-format mp3 \
  --quiet --no-warnings \
  -o "OUTPUT_PATH" \
  [--cookies PATH] \
  "URL"
```

Print output path, or `AUDIO_DOWNLOAD_FAILED` on error.

## Mode: video

Download full video (720p max, remuxed to mp4).

```bash
~/.claude/my-venvs/video-learn/bin/yt-dlp \
  -f "bestvideo[height<=720]+bestaudio/best[height<=720]/best" \
  --remux-video mp4 \
  --quiet --no-warnings \
  -o "OUTPUT_PATH" \
  [--cookies PATH] \
  "URL"
```

Print output path, or `VIDEO_DOWNLOAD_FAILED` on error.

## Step 2: Print result

```
[mode] → [result path or NO_SUBTITLES/FAILED]
```
