---
name: learn-everything
description: >
  Learning engine. Takes any input — video URL, local video/audio file, text file,
  or images — and produces structured learning notes. Detects content type and chains
  the appropriate pipeline automatically.
allowed-tools: Bash Read
argument-hint: <url-or-file-or-text> [--hint "free text"] [--video-frame-hint] [--lang LANG] [--cookies PATH]
effort: high
---

Input to learn from: $ARGUMENTS

## Step 1: Parse arguments

- `SOURCE` — URL, file path, or raw text
- `--hint TEXT` — content type and learning goals
- `--video-frame-hint` — request key frame extraction from video
- `--lang LANG` — language hint for transcript
- `--cookies PATH` — cookies file for sites requiring auth (e.g. Bilibili)

## Step 2: Detect input type

| Condition | Type |
|---|---|
| SOURCE is URL | video-url |
| SOURCE ends in .mp4 .mkv .mov .avi .webm | video-file |
| SOURCE ends in .mp3 .m4a .wav | audio-file |
| SOURCE ends in .md .txt | text-file |
| SOURCE ends in .jpg .png .gif .webp | image |

## Step 3: Prepare output directory

For video/audio input, fetch metadata to get the title and ID:
```bash
~/.claude/my-venvs/video-learn/bin/yt-dlp \
  --print "TITLE:%(title)s\nID:%(id)s" --no-download --no-playlist [--cookies PATH] "SOURCE" 2>/dev/null
```

Derive:
- `SLUG` — 3–5 words from title, lowercase, hyphen-separated (ignore channel names, brackets, episode numbers)
- `CLEAN_ID` — ID with leading dashes stripped and spaces replaced with hyphens
- `DIR_ROOT` — `./learn-everything-output/{SLUG}-{CLEAN_ID}/`

For text/image input: use a slug from the filename or first line of content.

Create output directory:
```bash
mkdir -p {DIR_ROOT}/transcription
```

If `./learn-everything-output/` did not exist before, warn user it was created.

Set paths:
- `TRANSCRIPT_PATH` = `{DIR_ROOT}/transcription/transcript.txt`
- `VIDEO_DIR` = `{DIR_ROOT}/video/`
- `FRAMES_DIR` = `{DIR_ROOT}/frames/`
- `ANALYSIS_PATH` = `{DIR_ROOT}/video-analysis.md`
- `TAKEAWAY_PATH` = `{DIR_ROOT}/takeaway.md`
- `NOTES_PATH` = `{DIR_ROOT}/notes.md`

## Step 4: Run pipeline

### Video input (video-url, video-file)

**4.1 — Transcribe**

Invoke `learn-everything:video-dl-transcribe` skill:
`SOURCE --output TRANSCRIPT_PATH [--lang LANG] [--cookies PATH]`

Read `COVERAGE` and `WARN` from the transcript header. COVERAGE is how much of the audio the
transcript accounts for, not how correct the words are — never treat a high score as accuracy.

A `WARN` on a transcript that was written is not a retry signal. Every chunk was transcribed; the
warning names a stretch of audio that produced no text, which means that stretch has no speech in
it. Note it for the user and keep going — re-running only spends the same minutes to get the same
answer.

Over music or sung/vocalised passages the transcript is most likely garbage — treat it as unreliable.

**→ Do not stop. Continue immediately to 4.2.**

**4.2 — Auto-detect frame extraction**

Skip if `--video-frame-hint` already passed.

Read TRANSCRIPT_PATH. Count signals:

| Signal | How to check |
|---|---|
| How-to / tutorial | Title or hint contains: tutorial, how-to, form, demo, workout, 动作, 教程, 展示, 演示 |
| Visual cue phrases | "look at", "as you can see", "here's the", "let me show", "this chart", "this slide", 看这里, 你看, 如图, 你可以看到 |
| On-screen content | Specific numbers/prices described as displayed, code on screen, spreadsheet/chart |

If 2+ signals → set `VIDEO_FRAME_HINT=true`.

**→ Do not stop. Continue immediately to 4.3.**

**4.3 — Download video (only if VIDEO_FRAME_HINT=true)**

```bash
ls "{VIDEO_DIR}/video.mp4" 2>/dev/null && echo "exists" || echo "missing"
```

If missing: invoke `learn-everything:video-dl-download` skill: `SOURCE --mode video --output {VIDEO_DIR}/video.%(ext)s [--cookies PATH]`
Also: `mkdir -p {VIDEO_DIR}` before downloading.

Set `VIDEO_PATH={VIDEO_DIR}/video.mp4`.

**→ Do not stop. Continue immediately to 4.4.**

**4.4 — Analyze video**

Invoke `learn-everything:learn-everything-video` skill:
`TRANSCRIPT_PATH --output ANALYSIS_PATH [--video VIDEO_PATH if VIDEO_FRAME_HINT] [--video-frame-hint if VIDEO_FRAME_HINT] [--frames-dir FRAMES_DIR if VIDEO_FRAME_HINT] [--hint HINT]`

**→ Do not stop. Continue immediately to 4.5.**

### Audio input (audio-file)

Run steps 4.1 and 4.4 only. Skip 4.2 and 4.3 (no frame extraction for audio).

### Text file or image input

Invoke `learn-everything:learn-everything-takeaway` skill: `SOURCE --output NOTES_PATH [--hint HINT]`
Then go to Step 5.

### Step 4.5 — Generate takeaway (video and audio)

Invoke `learn-everything:learn-everything-takeaway` skill:
`ANALYSIS_PATH --output TAKEAWAY_PATH [--hint HINT]`

**→ Do not stop. Continue immediately to 4.6.**

### Step 4.6 — Merge and finalize (video and audio)

```bash
cat ANALYSIS_PATH TAKEAWAY_PATH > NOTES_PATH
rm ANALYSIS_PATH TAKEAWAY_PATH
```

## Step 5: Print completion

```
Output: {NOTES_PATH}
```
