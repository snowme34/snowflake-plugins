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
| Apple Silicon | `mlx-whisper` (Metal GPU) | ~3x realtime per process, ~3 processes at once |
| Everything else | `faster-whisper` (CPU) | ~0.8x realtime, single process (it already uses every core) |

**Dense speech is much slower than sparse speech of the same length.** Whisper decodes token by token, so an hour of a talkative lecturer costs far more than an hour of a recording with pauses and music. Measure before promising anyone a finish time.

### Chunking

Whisper always runs chunked — at every length, with no flag to set. `get_transcript.py` cuts the audio into 5-minute spans, transcribes several at once (one process leaves the GPU mostly idle; three is several times the throughput), offsets each chunk's timestamps back onto the source timeline, and caches every finished chunk. So no run outlives a command timeout, and one that gets killed resumes for free.

**Every bug this plugin has had lived at a chunk boundary, and every one of them was silent.** Two separate mechanisms are needed, and it is easy to think the first is the whole story.

**The pad.** A chunk's audio window runs 10 seconds past the span it leads on, at both ends. A cut lands mid-word about as often as not, and Whisper handed audio that starts halfway through a syllable will invent a word or drop one. Hard-cutting a 6-minute excerpt at five points lost `比如说` and `反正你`, split `他就很 | 容易对吧` across two lines, and said `对吧` twice — five seams, five wounds, exit code 0.

**The cursor.** The pad alone is not enough, and believing otherwise cost this plugin a whole rewrite. Adjacent chunks decode their shared boundary region *independently and disagree about where a segment starts*: chunk 4 hears a sentence beginning at 300.9s, chunk 5 hears the same speech beginning at 299.0s. Ask each chunk "does this segment start inside my span?" against a boundary at 300.0s and **both answer no** — chunk 4 says it belongs to chunk 5, chunk 5 says it belongs to chunk 4, and the sentence is gone. That is not hypothetical: it deleted "还有一个概念叫低频、中频和高频" from a vocal-technique lecture, the sentence the rest of the lesson is built on, while the header cheerfully reported `COVERAGE: 1.00`. So the merge stitches with a cursor instead: a segment is taken whenever it ends past the last moment already transcribed. Audio can be transcribed twice — never zero times.

`scripts/test_get_transcript.py` locks both. `test_boundary_handover` replays the exact timestamps that produced that drop; revert the merge and it fails.

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
- **Speech recognition output is not ground truth.** Homophone errors are common, especially in Chinese and on domain jargon — a vocal-technique lecture in this repo's own test material has 声带 ("vocal folds") transcribed as 生态 ("ecology") throughout. The `COVERAGE` header does not see this and never will: it measures how completely the transcript spans the audio, not whether the words are right. Only `SOURCE` tells you a machine wrote it. When a line carries weight, check it against the audio — the timestamps are there so you can.
