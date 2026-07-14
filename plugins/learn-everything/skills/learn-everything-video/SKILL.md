---
name: learn-everything-video
description: >
  Analyzes a video transcript and produces a structured Markdown learning document with
  semantic chapters, timestamps, key transcript excerpts, and (optionally) key frames.
  Requires a transcript file produced by video-dl-transcribe.
allowed-tools: Bash Read
argument-hint: <transcript-path> [--video VIDEO_PATH] [--hint "free text"] [--video-frame-hint] [--output PATH] [--frames-dir PATH]
effort: high
---

Transcript: $ARGUMENTS

## Paths

| Resource | Path |
|---|---|
| Frame extraction script | `${CLAUDE_SKILL_DIR}/scripts/extract_frame.sh` |
| Default output | `./tmp-claude/video-report/video-analysis.md` |
| Default frames dir | `./tmp-claude/video-report/frames/` |

## Step 0: Parse arguments

- `TRANSCRIPT_PATH` — path to transcript file (required)
- `--video VIDEO_PATH` — local video file path (needed for frame extraction)
- `--hint TEXT` — free-text hint about content type and learning goals
- `--video-frame-hint` — extract key frames (requires --video)
- `--output PATH` — override default output path
- `--frames-dir PATH` — override default frames output directory

## Step 1: Read transcript

Load TRANSCRIPT_PATH. Extract header fields: `TITLE`, `DURATION`, `LANG`, `SOURCE`, `COVERAGE`.
Collect all timestamped lines (`[H:]M:SS text`) as the transcript body.

If `SOURCE` names a recogniser (`…-whisper/…` or `yt-dlp-auto/…`), the wording is machine-made:
proper nouns and technical terms are the first thing it gets wrong. Quote it as it stands — do
not silently "correct" it — but do not build a claim on a single odd-looking term.

## Step 2: Detect content type

Use hint (if provided) + TITLE + first 20 transcript lines:

| Content type | Detection signals |
|---|---|
| 教程 | "how to", "step", "let me show", 动作, 教程, 展示 |
| 概念讲解 | "explain", "what is", "understand", academic title |
| 访谈 | conversational exchange, Q&A, two voices |
| 新闻 | reporter tone, who/what/when/where |
| 讲座 | dense structured information, single authoritative voice |

If unclear after hint + title + first 20 lines, default to `讲座`.

## Step 3: Divide into semantic chapters

Group transcript lines into 2–6 minute topic segments. Use chapter markers from transcript header if present. Otherwise derive from topic shifts.

For each chapter: start/end timestamps, semantic title in Chinese, 3–8 representative transcript lines.

## Step 4: Identify visual moments (--video-frame-hint only)

Scan for visual cue phrases: "look at this", "as you can see", "here's the chart", 看这里, 你看, 如图, 你可以看到, specific numbers shown on-screen.

Collect `(timestamp_seconds, cue_text)` pairs. Also add chapter_start+2s and chapter_midpoint.

## Step 5: Extract frames (--video-frame-hint + --video required)

For each frame candidate:

Use FRAMES_DIR from `--frames-dir` if provided, otherwise default.

**Pass 1 — low-res verify:**
```bash
mkdir -p FRAMES_DIR
bash "${CLAUDE_SKILL_DIR}/scripts/extract_frame.sh" \
  VIDEO_PATH TIMESTAMP_SECS \
  "FRAMES_DIR/frame_NNN.jpg" \
  --low-res-only
```

View `.thumb.jpg`. KEEP if: chart, diagram, slide with data, code, graph, spreadsheet. SKIP if: talking head, black frame, transition.

If KEEP → run Pass 2 (same command without `--low-res-only`).
If SKIP → try TIMESTAMP ± 3s once. If still bad, skip.

## Step 6: Write the document

Output to OUTPUT_PATH (`--output` override or default).

```markdown
# {TITLE}

{SOURCE URL — only if online source, full URL}

时长：{N 分钟}
语言：{LANG}
分类：{content category — single label, e.g. 教程, 访谈, 概念讲解, 新闻, 讲座}
标签：{comma-separated topic tags specific to this video}

## [{MM:SS}–{MM:SS}] {Chapter Title}

{2–4 sentence factual summary. What is argued or shown? What evidence or example is used?}

> [{MM:SS}] "exact quote from transcript"
> [{MM:SS}] "exact quote from transcript"

![{description}](frames/frame_NNN.jpg)
*(~{MM:SS} — {what the frame shows})*

## [{MM:SS}–{MM:SS}] {Next Chapter}

...
```

Writing rules:
- All chapter titles, summaries, and labels in Simplified Chinese (简体中文)
- Transcript quotes in original source language — do not translate
- Chapter titles from actual content — never generic labels
- Transcript quotes are EXACT, not paraphrases
- Frame lines only if frame was actually extracted
- Summaries are factual — no interpretation
- Every specific in a summary — number, date, year range, named product, named person, percentage — must appear verbatim in that chapter's transcript quotes. If not, drop it.
- No horizontal rules between chapters
- No footer
