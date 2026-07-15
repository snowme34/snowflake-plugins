---
name: video-dl-transcribe
description: >
  Fetch a transcript from any video URL or local file. Tries platform subtitles first;
  falls back to Whisper speech recognition (GPU-accelerated on Apple Silicon) if unavailable.
allowed-tools: Bash Read
argument-hint: <url-or-file> [--lang LANG] [--model tiny|small|medium|large-v3|large-v3-turbo] [--cookies PATH] [--output PATH]
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

## Step 1: Parse arguments

- `INPUT` — the URL or local file path to transcribe (required)
- `--lang LANG` — the language being spoken (`en`, `zh`, `ja`). Pass it whenever you know it.
- `--model MODEL` — default `large-v3`. Go smaller only if the user asks for speed over accuracy.
- `--cookies PATH` — cookies file for sites that need auth
- `--output PATH` — override the default output path

Everything else the script decides for itself: captions vs speech recognition, GPU vs CPU backend,
chunking, worker count. `--chunk-minutes`, `--workers` and `--backend` exist for debugging one of
those decisions; leave them alone.

If INPUT is a Bilibili URL and `--cookies` was not given, default to
`~/.claude/my-auth/cookies-bilibili.txt`. If that file is missing, stop and say:
> ⚠ Bilibili requires cookies. Run the `learn-everything:video-dl-setup` skill for instructions.

## Step 2: Check the dependencies this run actually needs

A URL needs yt-dlp. A local file never touches it. Both need ffmpeg, and both need a Whisper
backend unless the captions happen to exist.

```bash
command -v ffmpeg >/dev/null && echo "ffmpeg=ok" || echo "ffmpeg=MISSING"
~/.claude/my-venvs/video-learn/bin/python - <<'PY'
import importlib.util as u
print("whisper=ok" if u.find_spec("mlx_whisper") or u.find_spec("faster_whisper") else "whisper=MISSING")
print("yt_dlp=ok" if u.find_spec("yt_dlp") else "yt_dlp=MISSING")
PY
```

`ffmpeg` or `whisper` missing → stop, tell the user to run `learn-everything:video-dl-setup`.
`yt_dlp` missing → only a problem if INPUT is a URL.

A YouTube video that reports **no caption tracks at all** simply has none — the uploader turned
them off. That is not a broken setup and there is nothing to fix; it means Whisper, and Whisper
means minutes. Tell the user that is why it is slow, rather than going looking for a bug.

## Step 3: Pick VIDEO_ID and the output path

- YouTube: the `v=` param, or the last path segment of a `youtu.be/` URL
- Bilibili: the `BV…` id in the path
- Local file: the filename without its extension
- Anything else: `~/.claude/my-venvs/video-learn/bin/yt-dlp --get-id "INPUT"`

`OUTPUT_PATH` = `--output` if given, else `./tmp-claude/video-grab/{VIDEO_ID}/transcript.txt`.

## Step 4: Run it

**Quote every path.** The files this gets pointed at have spaces and CJK characters in their
names; an unquoted `INPUT` splits into two arguments and argparse rejects it.

Captions come back in seconds, so a URL can run in the foreground. Speech recognition does not:
it runs at roughly 5–8× realtime on Apple Silicon and slower than realtime on CPU, so an hour of
audio takes many minutes and will outlive the foreground limit. **A local file always means speech
recognition — run it in the background.** So will a URL with no captions, which you cannot know in
advance; if a foreground URL run is still going after a minute, kill it and relaunch it this way.

Foreground (URL, expecting captions):

```bash
mkdir -p "$(dirname "OUTPUT_PATH")"
~/.claude/my-venvs/video-learn/bin/python \
  "${CLAUDE_SKILL_DIR}/scripts/get_transcript.py" \
  "INPUT" --output "OUTPUT_PATH" [--lang LANG] [--model MODEL] [--cookies PATH]
```

Background (local file, or a URL that fell back to Whisper) — use the Bash tool's
`run_in_background`, and add `2>&1` so the `PROGRESS:` lines land in the same log:

```bash
mkdir -p "$(dirname "OUTPUT_PATH")"
~/.claude/my-venvs/video-learn/bin/python \
  "${CLAUDE_SKILL_DIR}/scripts/get_transcript.py" \
  "INPUT" --output "OUTPUT_PATH" [--lang LANG] [--model MODEL] 2>&1
```

Then wait for the task to finish. Do not poll in a shell loop and do not re-launch it — the
harness tells you when a background task exits. `PROGRESS: done/total` in the log says how far
along it is if the user asks.

**If the run dies** (killed, timed out, machine slept): re-run the identical command. Finished
chunks are cached, and it picks up from where it stopped. This is the *only* situation in which
re-running helps.

## Step 5: Report

The command prints the transcript header to stdout. Note that the header's `SOURCE` field is the
*engine* that produced the transcript, not the input you gave it — do not report it as the origin.

```
Transcript: {header SOURCE}, lang={LANG}, coverage={COVERAGE}, {DURATION}s
Input: INPUT
Path: OUTPUT_PATH
```

| Header | Meaning | What you must do |
|---|---|---|
| `SOURCE: yt-dlp/…` | a human wrote these subtitles | trust the wording |
| `SOURCE: yt-dlp-auto/…` | YouTube's recogniser wrote them | ⚠ tell the user it is machine-generated |
| `SOURCE: …-whisper/…` | Whisper wrote them | ⚠ tell the user it is machine-generated |
| `WARN: …` | audio is missing from the transcript | print it verbatim, then read the rule below |
| no `DURATION` line | the source would not say how long it is | say so; do not report a duration of 0 |

`COVERAGE` is the fraction of the audio some transcript line accounts for — **not** how correct the
words are. A recogniser that mishears the same technical term for an hour still scores 1.00. Never
offer a high COVERAGE as evidence that the transcript is accurate.

**A `WARN` on a run that completed does not mean "try again."** The command already transcribed
every chunk; re-running repeats all of it and returns the same answer. `stops at …` or `a 300s
stretch … produced no text` on a completed run means that stretch of audio has no speech in it —
silence, music, or a truncated source file. Tell the user which stretch, and carry on with the
transcript you have.
