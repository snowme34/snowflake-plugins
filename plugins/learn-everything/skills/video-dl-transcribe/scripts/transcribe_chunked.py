#!/usr/bin/env python3
"""
Transcribe long audio in fixed-length chunks, resuming where a previous run stopped.

Whisper on a full-length recording can outlive any single command timeout. This splits the
audio with ffmpeg, transcribes one chunk at a time, caches each chunk's segments as JSON, and
merges them with timestamps offset back onto the original timeline. Re-running skips finished
chunks, so an interrupted run costs nothing to resume.

Usage:
  transcribe_chunked.py <AUDIO> --output PATH [--chunk-minutes N] [--lang LANG]
                        [--model MODEL] [--backend auto|mlx|faster] [--max-chunks N]

Prints CHUNKS_DONE: i/n each pass, and ALL_CHUNKS_DONE once the merged transcript is written.
Exit codes: 0=success (may be partial if --max-chunks stopped it early), 1=hard failure
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from get_transcript import (  # noqa: E402
    DEFAULT_MODEL,
    _fmt_ts,
    _transcribe_faster,
    _transcribe_mlx,
    assess_quality,
    pick_backend,
)

# A single Whisper process leaves the GPU mostly idle — it spends its time waiting, not computing.
# Running a few chunks side by side multiplies throughput; past ~4 they contend for memory bandwidth.
DEFAULT_WORKERS = 3


def audio_duration(path: str) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        print(f"ERROR: ffprobe failed on {path}: {r.stderr.strip()[:200]}", file=sys.stderr)
        sys.exit(1)
    return float(r.stdout.strip())


def extract_chunk(src: str, start: float, length: float, dest: Path) -> None:
    """Cut [start, start+length) to 16kHz mono wav — what Whisper wants anyway."""
    r = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", str(start), "-t", str(length),
         "-i", src, "-ac", "1", "-ar", "16000", "-y", str(dest)],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        print(f"ERROR: ffmpeg failed to cut chunk at {start}s: {r.stderr.strip()[:200]}", file=sys.stderr)
        sys.exit(1)


def run_worker(wav: str, lang: str | None, model: str, backend: str) -> None:
    """Child process: transcribe one chunk wav, leaving chunk-local timestamps for the parent."""
    transcribe = _transcribe_mlx if backend == "mlx" else _transcribe_faster
    result = transcribe(wav, lang, model)
    Path(wav).with_suffix(".raw.json").write_text(
        json.dumps({"lines": result["lines"], "lang": result["lang"]}, ensure_ascii=False),
        encoding="utf-8",
    )


def _finalize_chunk(cache_dir: Path, index: int, start: float, returncode: int) -> None:
    """Offset a finished chunk back onto the original timeline and commit it to the cache."""
    wav = cache_dir / f"chunk-{index:03d}.wav"
    raw = cache_dir / f"chunk-{index:03d}.raw.json"
    if returncode != 0 or not raw.exists():
        print(f"ERROR: chunk {index} failed (exit {returncode}). Re-run to retry it.", file=sys.stderr)
        sys.exit(1)

    data = json.loads(raw.read_text(encoding="utf-8"))
    lines = [(start + float(ts), text) for ts, text in data["lines"]]
    # Only now does chunk-NNN.json exist — a half-written chunk can never be mistaken for a done one.
    (cache_dir / f"chunk-{index:03d}.json").write_text(
        json.dumps({"lines": lines, "lang": data["lang"]}, ensure_ascii=False), encoding="utf-8",
    )
    raw.unlink()
    wav.unlink(missing_ok=True)


def run_pool(pending: list[tuple[int, float, float]], cache_dir: Path, n_chunks: int,
             args: argparse.Namespace, workers: int) -> None:
    queue = list(pending)
    running: dict[subprocess.Popen, tuple[int, float]] = {}

    while queue or running:
        while queue and len(running) < workers:
            index, start, length = queue.pop(0)
            cmd = [sys.executable, str(Path(__file__).resolve()), str(args.audio),
                   "--output", str(args.output), "--model", args.model, "--backend", args.backend,
                   "--worker-chunk", str(cache_dir / f"chunk-{index:03d}.wav")]
            if args.lang:
                cmd += ["--lang", args.lang]
            print(f"INFO: chunk {index + 1}/{n_chunks}  [{_fmt_ts(start)} → {_fmt_ts(start + length)}]",
                  file=sys.stderr)
            running[subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)] = (index, start)

        finished = [p for p in running if p.poll() is not None]
        if not finished:
            time.sleep(0.5)
            continue
        for proc in finished:
            index, start = running.pop(proc)
            _finalize_chunk(cache_dir, index, start, proc.returncode)


def main() -> None:
    parser = argparse.ArgumentParser(description="Chunked, resumable Whisper transcription")
    parser.add_argument("audio", help="Local audio/video file")
    parser.add_argument("--output", "-o", required=True, help="Merged transcript path")
    parser.add_argument("--chunk-minutes", type=float, default=15.0)
    parser.add_argument("--lang", default=None)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--backend", default="auto", choices=["auto", "mlx", "faster"])
    parser.add_argument("--max-chunks", type=int, default=0,
                        help="Transcribe at most N chunks this pass (0 = all). Re-run to continue.")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
                        help=f"Chunks to transcribe concurrently (default: {DEFAULT_WORKERS}). "
                             "One Whisper process does not saturate the GPU; 3-4 in parallel is "
                             "several times the throughput. Each holds the model in RAM (~1.6GB).")
    parser.add_argument("--worker-chunk", default=None, help=argparse.SUPPRESS)  # internal
    args = parser.parse_args()

    src = Path(args.audio)
    if not src.exists():
        print(f"ERROR: no such file: {src}", file=sys.stderr)
        sys.exit(1)

    backend = pick_backend(args.backend)

    if args.worker_chunk:
        run_worker(args.worker_chunk, args.lang, args.model, backend)
        return

    out_path = Path(args.output)
    cache_dir = out_path.parent / "chunks"
    cache_dir.mkdir(parents=True, exist_ok=True)

    duration = audio_duration(str(src))
    chunk_len = args.chunk_minutes * 60
    n_chunks = int(duration // chunk_len) + (1 if duration % chunk_len else 0)

    pending: list[tuple[int, float, float]] = []
    for i in range(n_chunks):
        if (cache_dir / f"chunk-{i:03d}.json").exists():
            continue
        if args.max_chunks and len(pending) >= args.max_chunks:
            break
        start = i * chunk_len
        pending.append((i, start, min(chunk_len, duration - start)))

    if pending:
        for i, start, length in pending:
            extract_chunk(str(src), start, length, cache_dir / f"chunk-{i:03d}.wav")
        run_pool(pending, cache_dir, n_chunks, args, max(1, args.workers))

    lang_seen = args.lang or "und"

    cached = sorted(cache_dir.glob("chunk-*.json"))
    print(f"CHUNKS_DONE: {len(cached)}/{n_chunks}")
    if len(cached) < n_chunks:
        print("INFO: re-run the same command to continue", file=sys.stderr)
        return

    lines: list[tuple[float, str]] = []
    for chunk_json in cached:
        data = json.loads(chunk_json.read_text(encoding="utf-8"))
        lines.extend((float(ts), text) for ts, text in data["lines"])
        if data.get("lang") and data["lang"] != "und":
            lang_seen = data["lang"]
    lines.sort(key=lambda x: x[0])

    quality, warn = assess_quality(lines, duration)
    header = [
        f"SOURCE: {backend}-whisper/{args.model} (chunked {args.chunk_minutes:g}min)",
        f"LANG: {lang_seen}",
        f"QUALITY: {quality}",
        f"TITLE: {src.stem}",
        f"DURATION: {int(duration)}",
    ]
    if warn:
        header.append(f"WARN: {warn}")
    body = [f"{_fmt_ts(ts)} {text}" for ts, text in lines]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(header + body), encoding="utf-8")
    print(f"SAVED: {out_path}")
    print("ALL_CHUNKS_DONE")


if __name__ == "__main__":
    main()
