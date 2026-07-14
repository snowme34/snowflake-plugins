#!/usr/bin/env python3
"""
Fetch a transcript for a video/audio URL or a local file.

Two ways to get one, in order:
  1. Platform captions via yt-dlp (URLs only) — instant and exact when they exist.
  2. Whisper speech recognition on the audio.

Whisper always runs chunked, at every length. Audio is cut into fixed spans, each span is
transcribed in its own process, and the timestamps are offset back onto the source timeline.
Finished chunks are cached, so an interrupted run resumes instead of starting over.

Two separate mechanisms keep a chunk boundary from eating words, and they are easy to confuse:

  The audio window of a chunk extends CHUNK_PAD_SECONDS past its span at both ends. A cut lands
  mid-word about as often as not, and Whisper fed audio that begins halfway through a syllable
  invents a word or drops one. The pad means the word is intact inside the audio of whichever
  chunk transcribes it.

  The merge then stitches chunks with a cursor (`merge_chunks`), because the pad alone is not
  enough. Adjacent chunks decode the boundary region *independently* and disagree about where a
  segment starts — one hears "他就很容易" starting at 299.0s, the next hears the same speech as
  starting at 300.9s. Attributing a segment to a chunk by its own reported start time therefore
  lets both chunks conclude the segment is the other's, and the sentence vanishes with no error
  and full COVERAGE. The cursor makes that impossible: a segment is taken whenever it ends past
  the last moment already transcribed, so audio can be transcribed twice but never zero times.

Backend picks itself: mlx-whisper (Metal GPU) on Apple Silicon, else faster-whisper (CPU).

Usage:
  get_transcript.py <URL_OR_FILE> [--output PATH] [--lang LANG] [--model MODEL]
                    [--backend auto|mlx|faster] [--force-whisper] [--cookies PATH]
                    [--chunk-minutes N] [--workers N]

Stdout — the header, always; the body only when --output is absent:
  SOURCE: yt-dlp/<lang> | yt-dlp-auto/<lang> | mlx-whisper/<model> | faster-whisper/<model>
  LANG: <code>
  COVERAGE: <0.00-1.00>
  TITLE: <title>
  DURATION: <seconds>      (omitted entirely when the source will not say)
  WARN: <message>          (only when something looks wrong with the result)
  [H:]M:SS text
  ...

`yt-dlp` means a human wrote those captions. `yt-dlp-auto` means YouTube's recogniser did —
as machine-generated as Whisper, and the header says so rather than hiding it behind the same
label as a real subtitle track.

COVERAGE is the fraction of the audio timeline that some transcript line accounts for. It says
nothing about whether the words are right: a recogniser that mishears one technical term for
another all the way through still scores 1.00. Only SOURCE tells you a machine wrote this.

Stderr — `PROGRESS: done/total` after every chunk. Speech recognition outlives any command
timeout on a long recording, so run it in the background and wait for the process to exit.
A run that was killed or timed out resumes from its cache; a run that *finished* has no cache
left to resume from, and re-running it only repeats the same work for the same answer.

Exit codes: 0 = transcript produced, 1 = failure.
"""
import argparse
import hashlib
import json
import math
import multiprocessing
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import NoReturn

# yt-dlp must be the one from this script's venv, not whatever is on PATH.
_YT_DLP = str(Path(sys.executable).parent / "yt-dlp")

DEFAULT_MODEL = "large-v3"
DEFAULT_CHUNK_MINUTES = 5.0
MIN_CHUNK_SECONDS = 60.0

# Each chunk's audio window runs this far past its span at both ends, so that a word lying on
# a cut is still heard whole by the chunk that transcribes it. Whisper's own segments run well
# under 10s on speech, so this is comfortably longer than anything it has to swallow.
CHUNK_PAD_SECONDS = 10.0

# Bumped whenever a change makes an old cached chunk wrong to reuse — a new segment schema, a
# different merge rule, a different offset. It is in the cache key, so old chunks are simply
# never found rather than silently merged by code that no longer means the same thing by them.
CACHE_FORMAT = 2

# Silence this long around a transcript line still counts as accounted-for: speakers pause.
# Anything longer is audio the transcript does not explain, and COVERAGE says so.
PAUSE_TOLERANCE_SECONDS = 5.0

# One Whisper process spends most of its time waiting on Python, not on the GPU; a few in
# parallel multiply throughput. Past ~4 they start fighting over memory bandwidth.
MLX_WORKERS = 3
# faster-whisper already spreads a single transcription across every core. A second process
# would only contend with the first.
FASTER_WORKERS = 1

# mlx-whisper takes an HF repo, not a size name.
_MLX_REPOS = {
    "tiny": "mlx-community/whisper-tiny-mlx",
    "base": "mlx-community/whisper-base-mlx",
    "small": "mlx-community/whisper-small-mlx",
    "medium": "mlx-community/whisper-medium-mlx",
    "large": "mlx-community/whisper-large-v3-mlx",
    "large-v3": "mlx-community/whisper-large-v3-mlx",
    "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
}

# faster-whisper has no large-v3-turbo; map our names onto what it does have.
_FASTER_SIZES = {
    "large": "large-v3",
    "large-v3-turbo": "large-v3",
}

_URL_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")

# How far back a rolling-caption cue may absorb an earlier one. Without a horizon, a short line
# that genuinely recurs later ("right", "对") gets deleted as a duplicate of an unrelated one
# from minutes ago.
ROLLING_HORIZON_SECONDS = 30.0

# A Whisper segment is one breath group, and a breath group is about this long once written
# down. Chinese fits a clause into ~8 characters where English needs ~35. Scoring both against
# a single number is what branded every Chinese transcript in this repo "moderate quality".
_EXPECTED_LINE_CHARS = {"cjk": 8.0, "latin": 35.0}


def die(message: str) -> NoReturn:
    print(f"ERROR: {message}", file=sys.stderr)
    sys.exit(1)


def fmt_ts(seconds: float) -> str:
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


# ---------------------------------------------------------------- backend


def pick_backend(requested: str) -> str:
    """Resolve 'auto' against what this machine actually has. Returns 'mlx' or 'faster'."""
    if requested != "auto":
        return requested
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        try:
            import mlx_whisper  # noqa: F401
        except ImportError:
            return "faster"
        return "mlx"
    return "faster"


def default_workers(backend: str) -> int:
    return MLX_WORKERS if backend == "mlx" else FASTER_WORKERS


def _transcribe_mlx(audio: str, lang: str | None, model: str) -> dict:
    import mlx_whisper

    repo = _MLX_REPOS.get(model, model)  # an unknown name is a caller-supplied HF repo
    result = mlx_whisper.transcribe(
        audio,
        path_or_hf_repo=repo,
        language=lang,
        condition_on_previous_text=False,  # a chunk otherwise spirals into repetition loops
        verbose=None,
    )
    segments = [
        (float(s["start"]), float(s["end"]), s["text"].strip())
        for s in result.get("segments", [])
        if s["text"].strip()
    ]
    return {"segments": segments, "lang": result.get("language") or lang}


@lru_cache(maxsize=1)
def _faster_model(size: str):
    """One model per worker process — constructing a WhisperModel costs seconds."""
    from faster_whisper import WhisperModel

    return WhisperModel(size, device="cpu", compute_type="int8")


def _transcribe_faster(audio: str, lang: str | None, model: str) -> dict:
    segments, info = _faster_model(_FASTER_SIZES.get(model, model)).transcribe(
        audio, beam_size=5, language=lang
    )
    parsed = [
        (float(s.start), float(s.end), s.text.strip()) for s in segments if s.text.strip()
    ]
    return {"segments": parsed, "lang": info.language or lang}


def run_whisper(audio: str, lang: str | None, model: str, backend: str) -> dict:
    if backend == "mlx":
        return _transcribe_mlx(audio, lang, model)
    return _transcribe_faster(audio, lang, model)


# ---------------------------------------------------------------- audio


def probe_duration(audio: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(audio)],
        capture_output=True, text=True,
    )
    raw = r.stdout.strip()
    try:
        duration = float(raw)
    except ValueError:
        die(f"ffprobe read no duration from {audio}: {r.stderr.strip()[:200] or raw or 'no output'}")
    if duration <= 0:
        die(f"{audio} reports a duration of {duration}s — not an audio file?")
    return duration


def extract_window(src: str, start: float, length: float, dest: Path) -> None:
    """Cut [start, start+length) to the 16 kHz mono WAV Whisper resamples to anyway."""
    r = subprocess.run(
        ["ffmpeg", "-v", "error", "-nostdin", "-ss", f"{start:.3f}", "-t", f"{length:.3f}",
         "-i", src, "-vn", "-ac", "1", "-ar", "16000", "-y", str(dest)],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg could not cut [{start:.1f}s +{length:.1f}s]: {r.stderr.strip()[:300]}")
    if not dest.exists() or dest.stat().st_size == 0:
        raise RuntimeError(f"ffmpeg produced no audio for [{start:.1f}s +{length:.1f}s]")


# ---------------------------------------------------------------- chunking


@dataclass(frozen=True)
class Chunk:
    """One unit of work: the span of the timeline it leads on, and the padded audio around it."""

    index: int
    start: float          # span this chunk leads on
    end: float
    window_start: float   # audio actually fed to Whisper — the span plus lead-in and lead-out
    window_end: float
    is_last: bool

    @property
    def limit(self) -> float:
        """First moment this chunk stops leading. The last chunk leads to the end of the audio.

        Segments starting at or after this are the next chunk's to lead on — it hears them from
        their beginning instead of from wherever this chunk's lead-out happens to stop.
        """
        return math.inf if self.is_last else self.end


def plan_chunks(duration: float, chunk_seconds: float) -> list[Chunk]:
    n = max(1, math.ceil(duration / chunk_seconds))
    return [
        Chunk(
            index=i,
            start=i * chunk_seconds,
            end=min((i + 1) * chunk_seconds, duration),
            window_start=max(0.0, i * chunk_seconds - CHUNK_PAD_SECONDS),
            window_end=min(duration, (i + 1) * chunk_seconds + CHUNK_PAD_SECONDS),
            is_last=(i == n - 1),
        )
        for i in range(n)
    ]


def chunk_json(cache: Path, index: int) -> Path:
    return cache / f"chunk-{index:04d}.json"


def transcribe_chunk(chunk: Chunk, audio: str, cache: str, lang: str | None,
                     model: str, backend: str) -> int:
    """Worker process. Cut, transcribe, put the timestamps back on the source timeline, cache.

    Every segment Whisper returns is cached, lead-in and lead-out included. The merge decides
    what to use; giving it the overlap is what lets it stitch chunks without a hole.
    """
    cache_dir = Path(cache)
    wav = cache_dir / f"chunk-{chunk.index:04d}.wav"
    try:
        extract_window(audio, chunk.window_start, chunk.window_end - chunk.window_start, wav)
        result = run_whisper(str(wav), lang, model, backend)
    finally:
        wav.unlink(missing_ok=True)

    segments = sorted(
        (chunk.window_start + start, chunk.window_start + end, text)
        for start, end, text in result["segments"]
    )
    payload = json.dumps({"segments": segments, "lang": result["lang"]}, ensure_ascii=False)

    # Write-then-rename: a chunk file exists only once it is complete, so a run killed mid-write
    # can never resume onto a truncated chunk.
    partial = cache_dir / f"chunk-{chunk.index:04d}.part"
    partial.write_text(payload, encoding="utf-8")
    partial.replace(chunk_json(cache_dir, chunk.index))
    return chunk.index


def merge_chunks(chunks: list[Chunk], cached: list[dict]) -> list[tuple[float, float, str]]:
    """Stitch chunks into one transcript, taking each moment of audio from the chunk that leads it.

    The rule that matters: a segment is taken whenever it ends past `covered` — the last moment
    already transcribed. Audio can therefore be transcribed twice, but never zero times.

    That asymmetry is the whole point. Adjacent chunks decode their shared boundary region
    independently and disagree about where a segment begins: chunk 4 hears a sentence starting at
    300.9s, chunk 5 hears the same sentence starting at 299.0s. Ask each chunk "is this start
    inside my span?" against a boundary at 300.0s and *both* answer no — chunk 4 says it is
    chunk 5's, chunk 5 says it is chunk 4's, and the sentence is gone. Silently, with COVERAGE
    still reporting 1.00. `covered` never moves backwards, so it cannot open that hole.
    """
    merged: list[tuple[float, float, str]] = []
    covered = 0.0
    for chunk, data in zip(chunks, cached):
        leading = False
        for start, end, text in data["segments"]:
            if start >= chunk.limit:
                break  # lead-out: the next chunk leads here, and heard it from the start
            if not leading and end <= covered:
                continue  # still in the lead-in the previous chunk already transcribed
            if not leading:
                # This is the hand-over. The segment reaches past `covered`, so it must be taken
                # or its tail of speech is lost — but it may also re-say the previous chunk's
                # last line or two in fuller form ("它还有" + "就是" → "它还有就是怎么说呢").
                # Give the region to the incoming chunk, which heard it as one continuous phrase,
                # and drop the outgoing chunk's now-redundant tail. Nothing is lost: this chunk
                # leads everything from here on, so whatever the popped lines said, its own
                # segments say again.
                while merged and merged[-1][0] >= start:
                    merged.pop()
                leading = True
            # Past the hand-over this chunk's segmentation is authoritative: Whisper lays a chunk
            # out as a monotonic, non-overlapping sequence, so every remaining segment is new
            # speech. Re-testing them against `covered` would drop one whenever Whisper's end
            # estimate for a line ran a hair past the start of the next.
            merged.append((start, end, text))
            covered = max(covered, end)
    return merged


def transcribe_all(audio: Path, duration: float, cache: Path, lang: str | None, model: str,
                   backend: str, chunk_seconds: float, workers: int
                   ) -> tuple[list[tuple[float, float, str]], str]:
    chunks = plan_chunks(duration, chunk_seconds)
    pending = [c for c in chunks if not chunk_json(cache, c.index).exists()]
    done = len(chunks) - len(pending)
    if done and pending:
        print(f"INFO: resuming — {done}/{len(chunks)} chunks already transcribed", file=sys.stderr)
    print(f"PROGRESS: {done}/{len(chunks)}", file=sys.stderr)

    if pending:
        print(f"INFO: {backend}-whisper/{model}, {len(pending)} chunks of "
              f"{chunk_seconds / 60:g}min, {min(workers, len(pending))} at a time", file=sys.stderr)
        # spawn, not fork: a forked child inherits a Metal/BLAS runtime it cannot safely reuse.
        context = multiprocessing.get_context("spawn")
        with ProcessPoolExecutor(max_workers=min(workers, len(pending)), mp_context=context) as pool:
            futures = {
                pool.submit(transcribe_chunk, c, str(audio), str(cache), lang, model, backend): c
                for c in pending
            }
            for future in as_completed(futures):
                chunk = futures[future]
                try:
                    future.result()
                except Exception as exc:  # noqa: BLE001 — name the chunk, then stop
                    for f in futures:
                        f.cancel()
                    print(f"ERROR: chunk {chunk.index} [{fmt_ts(chunk.start)}–{fmt_ts(chunk.end)}] "
                          f"failed: {exc}", file=sys.stderr)
                    print("INFO: finished chunks are cached — re-run the same command to retry the rest.",
                          file=sys.stderr)
                    sys.exit(1)
                done += 1
                print(f"PROGRESS: {done}/{len(chunks)}  "
                      f"[{fmt_ts(chunk.start)}–{fmt_ts(chunk.end)}]", file=sys.stderr)

    cached = [json.loads(chunk_json(cache, c.index).read_text(encoding="utf-8")) for c in chunks]
    spoken = [d["lang"] for d in cached if d["lang"]]
    detected = Counter(spoken).most_common(1)[0][0] if spoken else (lang or "und")
    return merge_chunks(chunks, cached), detected


# ---------------------------------------------------------------- cache


def cache_dir_for(identity: str, output: Path | None, model: str, backend: str,
                  chunk_seconds: float, lang: str | None) -> Path:
    """A cache directory only ever reusable by a run that would produce the same chunks.

    Everything that changes what a chunk contains is in the key, CACHE_FORMAT included. Two
    videos writing into one output directory, or the same video re-cut at a different chunk
    length, or a chunk written by an older merge contract, therefore cannot be resumed onto —
    which they would all silently be if the path were fixed.
    """
    fingerprint = json.dumps(
        [CACHE_FORMAT, identity, model, backend, chunk_seconds, CHUNK_PAD_SECONDS, lang or ""],
        sort_keys=True,
    )
    key = hashlib.sha1(fingerprint.encode()).hexdigest()[:12]
    root = output.parent if output else Path(tempfile.gettempdir())
    return root / f".transcribe-cache-{key}"


def source_identity(source: str, kind: str) -> str:
    """What the cache key must change with.

    For a local file that means the bytes, not just the path — size and mtime stand in for the
    content, so editing a file in place invalidates its chunks. For a URL it is only the URL:
    the cache exists to survive an interrupted run of *this* download, and it is deleted the
    moment the transcript is written, so there is no window in which stale remote content could
    be reused under an unchanged address.
    """
    if kind == "url":
        return source
    stat = Path(source).resolve().stat()
    return f"{Path(source).resolve()}|{stat.st_size}|{stat.st_mtime_ns}"


# ---------------------------------------------------------------- yt-dlp


def require_yt_dlp() -> None:
    if not Path(_YT_DLP).exists():
        die(f"yt-dlp not found at {_YT_DLP}. Run the learn-everything:video-dl-setup skill first.")


def _yt_dlp(args: list[str], cookies: str | None, timeout: int) -> subprocess.CompletedProcess:
    cmd = [_YT_DLP, "--no-warnings", "--no-playlist"]
    if cookies:
        cmd += ["--cookies", cookies]
    return subprocess.run(cmd + args, capture_output=True, text=True, timeout=timeout)


def fetch_metadata(url: str, cookies: str | None) -> dict:
    """Title, duration and the caption tables — one yt-dlp call, everything downstream needs it."""
    try:
        r = _yt_dlp(["--dump-json", "--skip-download", url], cookies, timeout=90)
    except subprocess.TimeoutExpired:
        die("yt-dlp timed out (90s) fetching metadata")
    if r.returncode != 0:
        die(f"yt-dlp could not read {url}: {r.stderr.strip()[:300] or 'no error output'}")
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        die(f"yt-dlp returned no usable metadata for {url}")


def _match_lang(table: dict, want: str) -> str | None:
    """Find `want` in a yt-dlp caption table, tolerating regional suffixes (zh → zh-Hans)."""
    if want in table:
        return want
    base = want.split("-")[0]
    return next((code for code in sorted(table) if code.split("-")[0] == base), None)


def pick_caption_lang(meta: dict, requested: str | None) -> tuple[str, bool] | None:
    """Which caption track to take — (lang, is_machine_generated) — or None to leave it to Whisper.

    Human subtitles beat machine ones. Beyond that, this never substitutes a language the caller
    did not ask for: given `--lang ja` on a video that only has English captions it returns None,
    so Whisper transcribes what is actually being said, rather than handing back an English
    transcript under a `LANG: ja` header.
    """
    manual = {k: v for k, v in (meta.get("subtitles") or {}).items() if k != "live_chat"}
    auto = meta.get("automatic_captions") or {}

    if requested:
        human = _match_lang(manual, requested)
        if human:
            return human, False
        machine = _match_lang(auto, requested)
        return (machine, True) if machine else None

    if manual:
        return sorted(manual)[0], False
    spoken = meta.get("language")
    machine = _match_lang(auto, spoken) if spoken else None
    return (machine, True) if machine else None


def fetch_captions(url: str, lang: str, cookies: str | None) -> list[tuple[float, float, str]] | None:
    with tempfile.TemporaryDirectory() as tmp:
        try:
            r = _yt_dlp(
                ["--write-subs", "--write-auto-subs", "--sub-langs", lang, "--sub-format", "vtt",
                 "--skip-download", "--quiet", "-o", str(Path(tmp) / "sub"), url],
                cookies, timeout=120,
            )
        except subprocess.TimeoutExpired:
            print("INFO: yt-dlp timed out (120s) fetching captions", file=sys.stderr)
            return None
        vtt = sorted(Path(tmp).glob("*.vtt"))
        if not vtt:
            print(f"INFO: no {lang} captions came back (exit {r.returncode})", file=sys.stderr)
            return None
        return parse_vtt(vtt[0].read_text(encoding="utf-8"))


def download_audio(url: str, cache: Path, cookies: str | None) -> Path:
    """Download once into the cache, so a resumed run does not pull an hour of audio again."""
    audio = cache / "source-audio.mp3"
    if audio.exists():
        print(f"INFO: reusing audio already downloaded to {audio}", file=sys.stderr)
        return audio

    print("INFO: downloading audio...", file=sys.stderr)
    try:
        r = _yt_dlp(
            ["-x", "--audio-format", "mp3", "--quiet", "-o", str(cache / "source-audio.%(ext)s"), url],
            cookies, timeout=1800,
        )
    except subprocess.TimeoutExpired:
        die("yt-dlp timed out (30min) downloading audio")
    if not audio.exists():
        die(f"yt-dlp downloaded no audio (exit {r.returncode}): {r.stderr.strip()[:300]}")
    return audio


# ---------------------------------------------------------------- VTT


def parse_vtt(text: str) -> list[tuple[float, float, str]]:
    cue = re.compile(
        r"(\d{1,2}):(\d{2}):(\d{2})\.(\d{3})\s+-->\s+(\d{1,2}):(\d{2}):(\d{2})\.(\d{3})"
    )
    cues: list[tuple[float, float, str]] = []
    span: tuple[float, float] | None = None
    parts: list[str] = []

    def secs(h: str, m: str, s: str, ms: str) -> float:
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000

    def flush() -> None:
        if span is None or not parts:
            return
        cleaned = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", " ".join(parts))).strip()
        if cleaned:
            cues.append((span[0], span[1], cleaned))

    for raw in text.splitlines():
        raw = raw.strip()
        m = cue.match(raw)
        if m:
            flush()
            g = m.groups()
            span, parts = (secs(*g[:4]), secs(*g[4:])), []
        elif raw and span is not None and not raw.isdigit():
            parts.append(raw)
    flush()
    return collapse_rolling(cues)


def collapse_rolling(cues: list[tuple[float, float, str]]) -> list[tuple[float, float, str]]:
    """Undo YouTube's rolling caption window.

    Auto-captions grow a sentence across consecutive cues — "A B", then "A B C", then "A B C D" —
    so the raw cue list says everything two or three times. Where one cue's text contains a recent
    one's, keep the longer text but the earlier start: the sentence began when it first appeared,
    not when it finished growing.
    """
    result: list[tuple[float, float, str]] = []
    for start, end, text in cues:
        absorbed = False
        for i in range(len(result) - 1, -1, -1):
            prev_start, prev_end, prev_text = result[i]
            if start - prev_start > ROLLING_HORIZON_SECONDS:
                break
            if text in prev_text:
                absorbed = True
                break
            if prev_text in text:
                result[i] = (prev_start, max(prev_end, end), text)
                absorbed = True
                break
        if not absorbed:
            result.append((start, end, text))
    return result


# ---------------------------------------------------------------- coverage


def _script_of(lines: list[tuple[float, float, str]]) -> str:
    text = "".join(t for _, _, t in lines)
    han = sum(1 for ch in text if "぀" <= ch <= "鿿")
    return "cjk" if han / len(text) > 0.2 else "latin"


def assess_coverage(lines: list[tuple[float, float, str]], duration: float) -> tuple[float, str]:
    """How much of the audio the transcript accounts for, 0.0–1.0, and what it leaves out.

    Coverage, not correctness. Nothing here can tell that a recogniser heard the wrong word — a
    transcript that mishears the same technical term for an hour scores 1.00.

    The score is one measured quantity, not a blend of proxies: the fraction of the timeline
    lying within PAUSE_TOLERANCE_SECONDS of some transcript line. That catches both ways a
    transcript goes missing — it stops early, or it has a hole in the middle — and a transcript
    of the first ten minutes of an hour cannot buy back a passing grade with the ten minutes it
    did get right.

    Two further faults do not belong in a coverage number but do belong in a warning: lines so
    sparse that speech is clearly being skipped, and lines so short they are stubs.
    """
    if not lines:
        return 0.0, "no transcript lines at all"
    if duration <= 0:
        return 0.0, "source duration unknown — coverage cannot be checked"

    covered = 0.0
    reach = 0.0  # right edge of the merged accounted-for interval so far
    largest_hole = 0.0
    hole_at = 0.0
    for start, end, _ in lines:
        left = max(0.0, start - PAUSE_TOLERANCE_SECONDS)
        right = min(duration, end + PAUSE_TOLERANCE_SECONDS)
        if left > reach:
            if reach > 0 and left - reach > largest_hole:
                largest_hole, hole_at = left - reach, reach
            covered += right - left
        else:
            covered += max(0.0, right - reach)
        reach = max(reach, right)
    score = round(min(1.0, covered / duration), 2)

    warnings = []
    tail = duration - reach
    if tail > max(60.0, 0.1 * duration):
        warnings.append(f"stops at {fmt_ts(lines[-1][1])} of {fmt_ts(duration)} — the last "
                        f"{int(tail)}s of audio produced no text")
    if largest_hole > max(60.0, 0.05 * duration):
        warnings.append(f"a {int(largest_hole)}s stretch from {fmt_ts(hole_at)} produced no text")

    avg_chars = sum(len(t) for _, _, t in lines) / len(lines)
    if avg_chars < 0.5 * _EXPECTED_LINE_CHARS[_script_of(lines)]:
        warnings.append(f"stubby: lines average {avg_chars:.0f} characters — check --lang")

    return score, "; ".join(warnings)


# ---------------------------------------------------------------- output


def classify_source(source: str) -> str:
    if _URL_RE.match(source):
        return "url"
    if Path(source).is_file():
        return "file"
    if Path(source).is_dir():
        die(f"that is a directory, not a media file: {source}")
    die(f"no such file, and not a URL: {source}")


def header_text(header: dict[str, str]) -> str:
    """Render the header, one `KEY: value` per line, dropping the fields with nothing to say.

    Values are flattened to a single line first. TITLE comes from the remote metadata of an
    arbitrary URL, and a title containing a newline would otherwise inject whatever it liked —
    a second `COVERAGE:` line, an empty `WARN:` — into a header the caller parses by line.
    """
    lines = []
    for key, value in header.items():
        flat = " ".join(str(value).split())
        if flat:
            lines.append(f"{key}: {flat}")
    return "\n".join(lines)


def render(header: dict[str, str], lines: list[tuple[float, float, str]]) -> str:
    body = [f"{fmt_ts(start)} {text}" for start, _, text in lines]
    return "\n".join([header_text(header)] + body)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch a transcript from a URL or a local file")
    parser.add_argument("source", help="URL, or path to a local video/audio file")
    parser.add_argument("--output", "-o", default=None, help="Write the transcript here")
    parser.add_argument("--lang", default=None, help="Language of the speech (e.g. en, zh, ja)")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"Whisper model (default: {DEFAULT_MODEL}). tiny/base/small/medium/"
                             "large-v3/large-v3-turbo, or an MLX HF repo.")
    parser.add_argument("--backend", default="auto", choices=["auto", "mlx", "faster"],
                        help="auto = mlx-whisper on Apple Silicon, faster-whisper elsewhere")
    parser.add_argument("--force-whisper", action="store_true",
                        help="Ignore platform captions and transcribe the audio")
    parser.add_argument("--cookies", default=None, help="Netscape cookies file (Bilibili needs one)")
    parser.add_argument("--chunk-minutes", type=float, default=DEFAULT_CHUNK_MINUTES,
                        help=f"Length of one Whisper chunk (default: {DEFAULT_CHUNK_MINUTES:g})")
    parser.add_argument("--workers", type=int, default=None,
                        help=f"Chunks transcribed at once (default: {MLX_WORKERS} on mlx, "
                             f"{FASTER_WORKERS} on faster-whisper). Each worker holds its own copy "
                             "of the model in memory (~1.6GB for large-v3).")
    args = parser.parse_args()

    chunk_seconds = args.chunk_minutes * 60
    if chunk_seconds < MIN_CHUNK_SECONDS:
        die(f"--chunk-minutes must be at least {MIN_CHUNK_SECONDS / 60:g}; shorter chunks are "
            f"mostly lead-in and lead-out padding")
    if args.workers is not None and args.workers < 1:
        die("--workers must be at least 1")

    kind = classify_source(args.source)
    output = Path(args.output) if args.output else None
    backend = pick_backend(args.backend)
    workers = args.workers or default_workers(backend)

    title = Path(args.source).stem if kind == "file" else ""
    duration = 0.0
    meta: dict = {}
    if kind == "url":
        require_yt_dlp()
        meta = fetch_metadata(args.source, args.cookies)
        title = meta.get("title") or ""
        duration = float(meta.get("duration") or 0)

    lines: list[tuple[float, float, str]] = []
    lang = args.lang or "und"
    label = ""

    if kind == "url" and not args.force_whisper:
        picked = pick_caption_lang(meta, args.lang)
        if picked:
            caption_lang, machine_made = picked
            lines = fetch_captions(args.source, caption_lang, args.cookies) or []
            if lines:
                lang = caption_lang
                label = f"yt-dlp-auto/{lang}" if machine_made else f"yt-dlp/{lang}"

    if not lines:
        if kind == "url":
            print("INFO: no usable captions — falling back to speech recognition", file=sys.stderr)
        cache = cache_dir_for(
            source_identity(args.source, kind), output, args.model, backend, chunk_seconds, args.lang
        )
        try:
            cache.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            # The cache lives beside --output, so an --output somewhere unwritable fails here
            # first — and would otherwise fail as a bare traceback from deep inside the run.
            die(f"cannot write next to {output}: {exc.strerror}")
        audio = download_audio(args.source, cache, args.cookies) if kind == "url" else Path(args.source)
        duration = probe_duration(audio)
        lines, lang = transcribe_all(audio, duration, cache, args.lang, args.model, backend,
                                     chunk_seconds, workers)
        label = f"{backend}-whisper/{args.model}"
        shutil.rmtree(cache, ignore_errors=True)

    coverage, warn = assess_coverage(lines, duration)
    header = {
        "SOURCE": label,
        "LANG": lang,
        "COVERAGE": f"{coverage}",
        "TITLE": title,
        # No duration is a fact worth saying out loud; `0` would be a lie the caller renders as
        # "0 minutes". header_text drops the field when there is nothing true to put in it.
        "DURATION": f"{int(duration)}" if duration > 0 else "",
        "WARN": warn,
    }

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(render(header, lines), encoding="utf-8")
        # The body is in the file. Echoing it here would only make the caller pay for it twice.
        print(header_text(header))
        print(f"SAVED: {output}")
    else:
        print(render(header, lines))


if __name__ == "__main__":
    main()
