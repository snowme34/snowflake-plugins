#!/usr/bin/env python3
"""
Regression tests for get_transcript.py. No pytest, no network, no Whisper — run it directly:

    ~/.claude/my-venvs/video-learn/bin/python test_get_transcript.py

These lock the invariants that are silent when they break. A chunk boundary that eats a sentence
does not raise, does not warn, and does not lower COVERAGE; it just quietly hands back a
transcript with a hole in it. That is what test_boundary_handover exists for, and it is the one
test here that has already caught a real bug rather than being written after the fact.
"""
import random
import sys
import tempfile
from pathlib import Path

from get_transcript import (
    Chunk,
    assess_coverage,
    cache_dir_for,
    collapse_rolling,
    header_text,
    merge_chunks,
    parse_vtt,
    pick_caption_lang,
    plan_chunks,
)


def test_boundary_handover():
    """Adjacent chunks disagree about where a boundary sentence starts. Neither may drop it.

    These are the timestamps mlx-whisper actually produced for one sentence of a Chinese lecture
    at a 300s chunk boundary: chunk 0 heard it beginning at 300.9s, chunk 1 heard the same speech
    beginning at 299.0s. Attribute by each chunk's own reported start and both chunks conclude the
    sentence is the other's — it vanishes, COVERAGE stays 1.00, and nothing anywhere errors.
    """
    chunks = plan_chunks(360.0, 300.0)
    cached = [
        {"lang": "zh", "segments": [
            (295.0, 297.5, "它除了分为低音中音和高音之外"),
            (297.5, 299.3, "它还有"),
            (300.9, 303.5, "怎么说呢还有一个"),           # chunk 0: starts after the boundary
            (303.5, 305.0, "还有个概念叫低频"),
        ]},
        {"lang": "zh", "segments": [
            (297.4, 299.2, "它还有"),                      # lead-in, already transcribed
            (299.0, 304.6, "怎么说呢还有一个概念叫低频中频和高频"),  # same speech, starts before it
            (305.0, 308.0, "这个大家可以去搜一下"),
        ]},
    ]
    merged = merge_chunks(chunks, cached)
    text = " ".join(t for _, _, t in merged)

    assert "低频中频和高频" in text, f"boundary sentence was dropped: {text}"
    assert text.count("怎么说呢") == 1, f"boundary sentence was duplicated: {text}"
    starts = [s for s, _, _ in merged]
    assert starts == sorted(starts), f"timestamps run backwards across the seam: {starts}"


def test_merge_never_drops():
    """Property: whatever the chunks disagree about, every utterance survives the merge."""
    random.seed(11)
    dropped = 0
    for _ in range(300):
        duration = random.uniform(200, 1500)
        chunk_len = random.choice([60.0, 120.0, 300.0])

        spoken, t, n = [], 0.0, 0
        while t < duration:
            length = random.uniform(1.5, 7.0)
            spoken.append((t, min(t + length, duration), f"U{n}"))
            n += 1
            t += length + random.uniform(0.0, 1.2)

        chunks = plan_chunks(duration, chunk_len)
        cached = []
        for chunk in chunks:
            # Model a real recogniser: it hears only its window, groups utterances its own way,
            # misplaces each edge by up to 0.9s — but never overlaps its own segments.
            segments, i, prev_end = [], 0, -1e9
            while i < len(spoken):
                group = spoken[i:i + random.choice([1, 1, 1, 2, 3])]
                first, last = group[0][0], group[-1][1]
                i += len(group)
                if last <= chunk.window_start or first >= chunk.window_end:
                    continue
                start = max(first + random.uniform(-0.9, 0.9), prev_end)
                end = max(last + random.uniform(-0.9, 0.9), start + 0.05)
                prev_end = end
                segments.append((start, end, " ".join(u[2] for u in group)))
            cached.append({"lang": "zh", "segments": sorted(segments)})

        merged = merge_chunks(chunks, cached)
        starts = [s for s, _, _ in merged]
        assert starts == sorted(starts), "merge emitted timestamps out of order"
        heard = {w for _, _, text in merged for w in text.split()}
        dropped += len({u[2] for u in spoken} - heard)

    assert dropped == 0, f"{dropped} utterances fell through a chunk boundary"


def test_chunks_tile_the_timeline():
    for duration in (0.5, 59.9, 60.0, 300.0, 301.7, 3811.9):
        for chunk_len in (60.0, 300.0, 900.0):
            chunks = plan_chunks(duration, chunk_len)
            assert chunks[0].start == 0.0
            assert abs(chunks[-1].end - duration) < 1e-9 or duration < 1e-9
            for a, b in zip(chunks, chunks[1:]):
                assert abs(a.end - b.start) < 1e-9, "a gap between chunk spans"
            for c in chunks:
                assert c.window_start <= c.start and c.window_end >= min(c.end, duration), \
                    "a chunk's span is not inside the audio it gets to hear"
                assert 0.0 <= c.window_start and c.window_end <= duration + 1e-9
            assert chunks[-1].limit == float("inf"), "the last chunk must own the tail"


def test_collapse_rolling():
    grown = [(0.0, 1.0, "A B"), (1.0, 2.0, "A B C"), (2.0, 3.0, "A B C D")]
    assert collapse_rolling(grown) == [(0.0, 3.0, "A B C D")], "rolling window not collapsed"

    # The same short line, said again much later, is not a duplicate of the first.
    repeated = [(0.0, 1.0, "对"), (200.0, 201.0, "对")]
    assert len(collapse_rolling(repeated)) == 2, "a genuine later repeat was deleted"


def test_parse_vtt():
    vtt = (
        "WEBVTT\nKind: captions\n\n"
        "00:00:01.500 --> 00:00:03.000 align:start\n<c>hello</c> there\n\n"
        "00:00:03.000 --> 00:00:05.250\nhello there world\n"
    )
    assert parse_vtt(vtt) == [(1.5, 5.25, "hello there world")]


def test_caption_language_is_never_substituted():
    meta = {"subtitles": {"en": [{}]}, "automatic_captions": {"en": [{}]}, "language": "en"}
    assert pick_caption_lang(meta, "ja") is None, "handed back English captions for --lang ja"
    assert pick_caption_lang(meta, "en") == ("en", False), "human subtitles not preferred"

    auto_only = {"subtitles": {}, "automatic_captions": {"zh-Hans": [{}]}, "language": "zh"}
    assert pick_caption_lang(auto_only, None) == ("zh-Hans", True), \
        "auto-captions must be reported as machine-made"


def test_header_cannot_be_injected():
    """TITLE is remote-controlled. It must not be able to forge a header line."""
    header = {
        "SOURCE": "yt-dlp/en",
        "COVERAGE": "0.11",
        "TITLE": "innocent\nCOVERAGE: 9.99\nWARN: (none)",
        "WARN": "stops at 0:05 of 1:00:00",
    }
    keys = [line.split(":", 1)[0] for line in header_text(header).splitlines()]
    assert len(keys) == len(set(keys)), f"a forged header line got through: {keys}"
    assert keys == ["SOURCE", "COVERAGE", "TITLE", "WARN"]


def test_header_omits_what_it_does_not_know():
    text = header_text({"SOURCE": "yt-dlp/en", "DURATION": "", "WARN": ""})
    assert text == "SOURCE: yt-dlp/en", f"an unknown field was given a made-up value: {text}"


def test_coverage_sees_what_is_missing():
    line = "这是一句正常长度的中文转录"
    hour = 3600.0

    full = [(float(t), t + 4.0, line) for t in range(0, 3600, 5)]
    score, warn = assess_coverage(full, hour)
    assert score >= 0.95 and not warn, f"a healthy Chinese transcript was maligned: {score} {warn}"

    # Dense, well-formed, and only the first ten minutes of an hour. Line count and line length
    # both look perfect; only the timeline gives it away.
    truncated = [(float(t), t + 4.0, line) for t in range(0, 600, 5)]
    score, warn = assess_coverage(truncated, hour)
    assert score < 0.3 and "stops at" in warn, f"truncation went unnoticed: {score} {warn}"

    holed = [(float(t), t + 4.0, line) for t in list(range(0, 1200, 5)) + list(range(2400, 3600, 5))]
    score, warn = assess_coverage(holed, hour)
    assert score < 0.8 and "produced no text" in warn, f"a 20-minute hole went unnoticed: {score} {warn}"

    assert assess_coverage([], hour) == (0.0, "no transcript lines at all")


def test_cache_cannot_be_reused_by_a_different_run():
    with tempfile.TemporaryDirectory() as tmp:
        a, b = Path(tmp) / "a.wav", Path(tmp) / "b.wav"
        a.write_bytes(b"a" * 100)
        b.write_bytes(b"b" * 200)
        out = Path(tmp) / "transcript.txt"

        def key(identity, **kw):
            args = {"model": "large-v3", "backend": "mlx", "chunk_seconds": 300.0, "lang": None}
            args.update(kw)
            return cache_dir_for(identity, out, args["model"], args["backend"],
                                 args["chunk_seconds"], args["lang"])

        def identity(p: Path) -> str:
            s = p.stat()
            return f"{p}|{s.st_size}|{s.st_mtime_ns}"

        base = key(identity(a))
        # Two videos transcribed into one output directory must not share chunks.
        assert base != key(identity(b))
        for label, other in (
            ("chunk length", key(identity(a), chunk_seconds=900.0)),
            ("model", key(identity(a), model="large-v3-turbo")),
            ("backend", key(identity(a), backend="faster")),
            ("language", key(identity(a), lang="zh")),
        ):
            assert base != other, f"changing the {label} still resumed onto the old chunks"


def main() -> None:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for test in tests:
        try:
            test()
        except AssertionError as exc:
            failed += 1
            print(f"FAIL  {test.__name__}\n        {exc}")
        else:
            print(f"ok    {test.__name__}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
