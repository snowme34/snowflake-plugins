# learn-everything

Turn any video, audio, or text into structured learning notes — with timestamps precise enough to jump back to the source.

Point it at a YouTube URL, a lecture recording, a PDF-turned-markdown, or a folder of screenshots. It detects the input type, runs the right pipeline, and writes notes you can actually study from: semantic chapters, verbatim quotes anchored to exact timestamps, and active-recall questions at the end.

## Usage

```
Learn everything from https://youtube.com/watch?v=...
Learn everything from ./lecture.m4a — I need exact timestamps
```

Or invoke a stage directly:

```
/learn-everything            # full pipeline (auto-detects input type)
/video-dl-transcribe         # just the transcript
/learn-everything-takeaway   # just the distillation, from any text
```

## Setup

One time, before first use:

```
/video-dl-setup
```

It creates a shared venv at `~/.claude/my-venvs/video-learn/` and installs `yt-dlp`, `faster-whisper`, and — on Apple Silicon — `mlx-whisper`. It also checks for `ffmpeg`, which you must install yourself (`brew install ffmpeg`).

The venv lives outside the plugin on purpose: it holds a multi-GB model cache that has no business inside a git repo.

## Speech recognition

Transcription picks its backend automatically:

| Platform | Backend | Throughput (large-v3) |
|---|---|---|
| Apple Silicon | `mlx-whisper` (Metal GPU) | ~3x realtime, ~13x with `--workers 3` |
| Everything else | `faster-whisper` (CPU) | ~0.8x realtime |

Two things worth knowing, because they cost real wall-clock time if you get them wrong:

**One Whisper process does not saturate the GPU.** It spends most of its life waiting. Running three chunks side by side is several times the throughput of one — measured on an M4, 1.7x realtime became 13.6x. This is what `--workers` is for, and it is the single biggest speed lever in the plugin.

**Dense speech is much slower than sparse speech of the same length.** Whisper decodes token by token, so an hour of a talkative lecturer costs far more than an hour of a recording with pauses and music. Measure one chunk before promising anyone a finish time.

For anything longer than ~10 minutes, use `transcribe_chunked.py` rather than a single pass. It splits with ffmpeg, transcribes chunks in parallel, offsets each chunk's timestamps back onto the original timeline, and caches every finished chunk — so no single command outlives its timeout, and an interrupted run resumes for free.

## Skills

| Skill | What it does |
|---|---|
| `learn-everything` | Orchestrator. Detects input type and chains the right pipeline. **Start here.** |
| `learn-everything-video` | Transcript → semantic chapters, timestamps, key frames |
| `learn-everything-takeaway` | Any content → retention-oriented notes with active-recall prompts |
| `learn-everything-market-news` | Thin wrapper for daily stock/market-review videos (Chinese output) |
| `video-dl-setup` | One-time environment setup |
| `video-dl-transcribe` | URL or local file → transcript (platform subtitles first, Whisper fallback) |
| `video-dl-download` | yt-dlp wrapper — metadata, subtitles, audio, or video |

## Notes

- **Bilibili needs cookies.** Export them to `~/.claude/my-auth/cookies-bilibili.txt`; without them every download fails with HTTP 412. `/video-dl-setup` explains how.
- **Speech recognition output is not ground truth.** Homophone errors are common, especially in Chinese and on domain jargon. When a transcript line carries weight, check it against the source — the timestamps are there so you can.
