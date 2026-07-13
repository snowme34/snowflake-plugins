#!/usr/bin/env python3
"""
Fetch video transcript. Tries yt-dlp captions first, falls back to local speech recognition.

Speech recognition backend is picked automatically:
  - Apple Silicon: mlx-whisper (Metal GPU, ~3x realtime on large-v3)
  - everything else: faster-whisper (CPU)

Usage:
  get_transcript.py <URL_OR_FILE> [--lang LANG] [--model MODEL] [--backend auto|mlx|faster]
                    [--output PATH] [--force-whisper] [--cookies PATH]

Stdout format:
  SOURCE: yt-dlp|mlx-whisper/<model>|faster-whisper/<model>
  LANG: <code>
  QUALITY: <0.00-1.00>
  TITLE: <title if available>
  DURATION: <seconds>
  WARN: <message>         (only if quality issue detected)
  [H:]M:SS text line
  ...

Exit codes: 0=success, 1=hard failure
"""
import argparse
import json
import platform
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# Use yt-dlp from same venv as this script, not from system PATH
_VENV_BIN = Path(sys.executable).parent
_YT_DLP = str(_VENV_BIN / "yt-dlp")

DEFAULT_MODEL = "large-v3"

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

# faster-whisper has no large-v3-turbo; map our defaults onto what it does have.
_FASTER_SIZES = {
    "large-v3": "large-v3",
    "large-v3-turbo": "large-v3",
    "large": "large-v3",
}


def _is_apple_silicon() -> bool:
    return platform.system() == "Darwin" and platform.machine() == "arm64"


def _mlx_available() -> bool:
    try:
        import mlx_whisper  # noqa: F401
    except ImportError:
        return False
    return True


def pick_backend(requested: str) -> str:
    """Resolve 'auto' to the best available backend. Returns 'mlx' or 'faster'."""
    if requested != "auto":
        return requested
    if _is_apple_silicon() and _mlx_available():
        return "mlx"
    return "faster"


def _check_yt_dlp() -> None:
    if not Path(_YT_DLP).exists():
        print(f"ERROR: yt-dlp not found at {_YT_DLP}. Run the learn-everything:video-dl-setup skill first.", file=sys.stderr)
        sys.exit(1)


def _fmt_ts(seconds: float) -> str:
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def fetch_yt_captions(url_or_file: str, lang: str | None, cookies: str | None = None) -> dict | None:
    """Try yt-dlp to get subtitles. Returns dict with keys: lines, lang, title, duration. None on failure."""
    if Path(url_or_file).exists():
        return None  # local file — no captions to fetch

    with tempfile.TemporaryDirectory() as tmp:
        out_tmpl = str(Path(tmp) / "sub")
        cmd = [
            _YT_DLP,
            "--write-auto-sub", "--write-sub",
            "--sub-format", "vtt",
            "--skip-download",
            "--no-warnings", "--quiet",
            "-o", out_tmpl,
        ]
        if lang:
            cmd += ["--sub-lang", lang]
        if cookies:
            cmd += ["--cookies", cookies]
        cmd.append(url_or_file)

        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired:
            print("INFO: yt-dlp captions timed out after 60s", file=sys.stderr)
            return None
        vtt_files = list(Path(tmp).glob("*.vtt"))
        if not vtt_files:
            if r.returncode != 0:
                print(f"INFO: yt-dlp captions failed (exit {r.returncode}): {r.stderr.strip()[:200]}", file=sys.stderr)
            return None

        vtt_path = vtt_files[0]
        detected_lang = re.search(r'\.([a-z]{2,3}(-\w+)?)\.vtt$', vtt_path.name)
        lang_code = detected_lang.group(1) if detected_lang else (lang or "und")

        lines = _parse_vtt(vtt_path.read_text(encoding="utf-8"))

        title, duration = "", 0
        meta_cmd = [_YT_DLP, "--dump-json", "--quiet", "--no-warnings"]
        if cookies:
            meta_cmd += ["--cookies", cookies]
        meta_cmd.append(url_or_file)
        meta_r = subprocess.run(meta_cmd, capture_output=True, text=True, timeout=60)
        if meta_r.returncode == 0 and meta_r.stdout.strip():
            try:
                meta = json.loads(meta_r.stdout)
                title = meta.get("title", "")
                duration = meta.get("duration", 0)
            except json.JSONDecodeError:
                pass

        return {"lines": lines, "lang": lang_code, "title": title, "duration": duration}


def _parse_vtt(vtt_text: str) -> list[tuple[float, str]]:
    """Parse VTT into list of (start_seconds, text). Deduplicates overlapping lines."""
    timestamp_re = re.compile(
        r'(\d{1,2}):(\d{2}):(\d{2})\.(\d{3})\s+-->\s+'
        r'(\d{1,2}):(\d{2}):(\d{2})\.(\d{3})'
    )
    lines: list[tuple[float, str]] = []
    seen_texts: set[str] = set()
    current_start: float | None = None
    current_text_parts: list[str] = []

    for raw_line in vtt_text.splitlines():
        raw_line = raw_line.strip()
        m = timestamp_re.match(raw_line)
        if m:
            if current_start is not None and current_text_parts:
                text = _clean_vtt_text(" ".join(current_text_parts))
                if text and text not in seen_texts:
                    lines.append((current_start, text))
                    seen_texts.add(text)
            h, mi, s, ms = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
            current_start = h * 3600 + mi * 60 + s + ms / 1000
            current_text_parts = []
        elif raw_line and not raw_line.startswith("WEBVTT") and "-->" not in raw_line and not raw_line.isdigit():
            current_text_parts.append(raw_line)

    if current_start is not None and current_text_parts:
        text = _clean_vtt_text(" ".join(current_text_parts))
        if text and text not in seen_texts:
            lines.append((current_start, text))

    return _deduplicate_rolling(lines)


def _deduplicate_rolling(lines: list[tuple[float, str]]) -> list[tuple[float, str]]:
    """Remove rolling-window artifacts from YouTube auto-captions.

    YouTube VTT rolling captions repeat partial sentences across adjacent timestamps
    as the caption window slides (e.g. "A B C" then "B C" then "B C D").
    Keep only the longest unique version within a sliding window of recent lines.
    """
    result: list[tuple[float, str]] = []
    for ts, text in lines:
        absorbed = False
        for i in range(len(result) - 1, max(len(result) - 6, -1), -1):
            prev_ts, prev_text = result[i]
            if text in prev_text:
                # already fully covered by a longer recent line — drop
                absorbed = True
                break
            if prev_text in text:
                # current line extends a recent one — replace with the longer version
                result[i] = (ts, text)
                absorbed = True
                break
        if not absorbed:
            result.append((ts, text))
    return result


def _clean_vtt_text(text: str) -> str:
    text = re.sub(r'<[^>]+>', '', text)   # strip VTT inline tags
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _fetch_audio(url_or_file: str, tmp: str, cookies: str | None) -> str:
    """Return a local audio path, downloading from the URL if needed."""
    if Path(url_or_file).exists():
        return url_or_file

    audio_out = str(Path(tmp) / "audio.%(ext)s")
    dl_cmd = [_YT_DLP, "-x", "--audio-format", "mp3", "--quiet", "--no-warnings", "-o", audio_out]
    if cookies:
        dl_cmd += ["--cookies", cookies]
    dl_cmd.append(url_or_file)
    try:
        r = subprocess.run(dl_cmd, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        print("ERROR: yt-dlp audio download timed out after 300s", file=sys.stderr)
        sys.exit(1)
    audio_files = list(Path(tmp).glob("audio.*"))
    if not audio_files:
        print(f"ERROR: yt-dlp audio download failed (exit {r.returncode}): {r.stderr[:200]}", file=sys.stderr)
        sys.exit(1)
    return str(audio_files[0])


def _transcribe_mlx(audio_path: str, lang: str | None, model: str) -> dict:
    import mlx_whisper

    repo = _MLX_REPOS.get(model, model)  # unknown name = caller passed an HF repo directly
    print(f"INFO: mlx-whisper '{repo}' on Metal GPU...", file=sys.stderr)
    result = mlx_whisper.transcribe(
        audio_path,
        path_or_hf_repo=repo,
        language=lang or None,
        condition_on_previous_text=False,  # long recordings otherwise spiral into repetition loops
        verbose=None,
    )
    segments = result.get("segments", [])
    lines = [(s["start"], s["text"].strip()) for s in segments if s["text"].strip()]
    duration = segments[-1]["end"] if segments else 0
    return {"lines": lines, "lang": result.get("language", lang or "und"), "title": "", "duration": duration}


def _transcribe_faster(audio_path: str, lang: str | None, model: str) -> dict:
    from faster_whisper import WhisperModel

    size = _FASTER_SIZES.get(model, model)
    print(f"INFO: faster-whisper '{size}' on CPU (slow — no GPU backend available)...", file=sys.stderr)
    whisper = WhisperModel(size, device="cpu", compute_type="int8")
    segments, info = whisper.transcribe(audio_path, beam_size=5, language=lang or None)

    segment_list = list(segments)
    lines = [(seg.start, seg.text.strip()) for seg in segment_list if seg.text.strip()]
    duration = segment_list[-1].end if segment_list else 0
    return {"lines": lines, "lang": info.language, "title": "", "duration": duration}


def transcribe_with_whisper(url_or_file: str, lang: str | None, model: str, backend: str,
                            cookies: str | None = None) -> tuple[dict, str]:
    """Transcribe locally. Returns (result, source_label). Downloads audio first if URL."""
    with tempfile.TemporaryDirectory() as tmp:
        audio_path = _fetch_audio(url_or_file, tmp, cookies)
        if backend == "mlx":
            return _transcribe_mlx(audio_path, lang, model), f"mlx-whisper/{model}"
        return _transcribe_faster(audio_path, lang, model), f"faster-whisper/{model}"


def assess_quality(lines: list[tuple[float, str]], duration: float) -> tuple[float, str]:
    """Score transcript quality 0.0–1.0. Returns (score, warning_message)."""
    if not lines:
        return 0.0, "No transcript lines found"

    coverage_score = min(1.0, len(lines) / max(1, duration / 10)) if duration > 0 else 0.7
    avg_len = sum(len(t) for _, t in lines) / len(lines)
    length_score = min(1.0, avg_len / 40)
    score = round((coverage_score * 0.6) + (length_score * 0.4), 2)

    if score < 0.4:
        warn = f"Low quality (score={score}): sparse or very short lines. Try --model large-v3."
    elif score < 0.65:
        warn = f"Moderate quality (score={score}): some gaps or short lines."
    else:
        warn = ""

    return score, warn


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch video transcript")
    parser.add_argument("source", help="URL or local video/audio file")
    parser.add_argument("--lang", default=None, help="Language code hint (e.g. en, zh, ja)")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"Whisper model if speech recognition is needed (default: {DEFAULT_MODEL}). "
                             "Sizes: tiny/base/small/medium/large-v3/large-v3-turbo, or an MLX HF repo.")
    parser.add_argument("--backend", default="auto", choices=["auto", "mlx", "faster"],
                        help="Speech recognition backend. auto = mlx-whisper on Apple Silicon, else faster-whisper.")
    parser.add_argument("--output", "-o", default=None, help="Also save transcript to this path")
    parser.add_argument("--force-whisper", action="store_true",
                        help="Skip yt-dlp captions, always use speech recognition")
    parser.add_argument("--cookies", default=None, help="Path to Netscape cookies file (e.g. for Bilibili)")
    args = parser.parse_args()

    _check_yt_dlp()

    result: dict | None = None
    source_label = "yt-dlp"

    if not args.force_whisper:
        result = fetch_yt_captions(args.source, args.lang, args.cookies)

    if not result or not result["lines"]:
        backend = pick_backend(args.backend)
        print("INFO: No captions from yt-dlp, falling back to speech recognition...", file=sys.stderr)
        result, source_label = transcribe_with_whisper(args.source, args.lang, args.model, backend, args.cookies)
        print(f"ALERT: Used local speech recognition ({source_label}). Verify accuracy.", file=sys.stderr)

    # Whisper fallback returns empty title — fetch it from yt-dlp for URLs
    if not result.get("title") and not Path(args.source).exists():
        try:
            title_cmd = [_YT_DLP, "--get-title", "--no-warnings", "--quiet"]
            if args.cookies:
                title_cmd += ["--cookies", args.cookies]
            title_cmd.append(args.source)
            tr = subprocess.run(title_cmd, capture_output=True, text=True, timeout=30)
            if tr.returncode == 0:
                result["title"] = tr.stdout.strip().splitlines()[0]
        except subprocess.TimeoutExpired:
            pass

    lines = result["lines"]
    quality, warn = assess_quality(lines, result.get("duration", 0))

    output_lines = [
        f"SOURCE: {source_label}",
        f"LANG: {result['lang']}",
        f"QUALITY: {quality}",
        f"TITLE: {result.get('title', '')}",
        f"DURATION: {int(result.get('duration', 0))}",
    ]
    if warn:
        output_lines.append(f"WARN: {warn}")
    for ts, text in lines:
        output_lines.append(f"{_fmt_ts(ts)} {text}")

    output = "\n".join(output_lines)
    print(output)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output, encoding="utf-8")
        print(f"SAVED: {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
