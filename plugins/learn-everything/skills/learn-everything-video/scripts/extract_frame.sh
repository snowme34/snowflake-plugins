#!/usr/bin/env bash
# Extract a single frame from a video file using two-pass approach.
#
# Usage:
#   extract_frame.sh <video_file> <timestamp_secs> <output_path> [--low-res-only]
#
# Pass 1: extract low-res (320px wide) for quick visual check.
# Pass 2 (default): extract full-res if not --low-res-only.
#
# Output files:
#   <output_path>             full-res JPEG (unless --low-res-only)
#   <output_path>.thumb.jpg   low-res JPEG (always written)
#
# Stdout: FRAME_OK: <path> or FRAME_OK_LOWRES: <path> or FRAME_FAIL: <reason>
# Exit codes: 0=success, 1=hard failure, 2=soft failure (seek out of range)

set -euo pipefail

VIDEO_FILE="${1:-}"
TIMESTAMP="${2:-}"
OUTPUT_PATH="${3:-}"
LOW_RES_ONLY="${4:-}"

if [[ -z "$VIDEO_FILE" || -z "$TIMESTAMP" || -z "$OUTPUT_PATH" ]]; then
    echo "Usage: extract_frame.sh <video_file> <timestamp_secs> <output_path> [--low-res-only]" >&2
    exit 1
fi

if [[ ! -f "$VIDEO_FILE" ]]; then
    echo "FRAME_FAIL: video file not found: $VIDEO_FILE"
    exit 1
fi

if ! command -v ffmpeg &>/dev/null; then
    echo "FRAME_FAIL: ffmpeg not found — run the learn-everything:video-dl-setup skill"
    exit 1
fi

mkdir -p "$(dirname "$OUTPUT_PATH")"
THUMB_PATH="${OUTPUT_PATH}.thumb.jpg"

# Pass 1: low-res thumbnail for visual verification
if ! ffmpeg -ss "$TIMESTAMP" -i "$VIDEO_FILE" \
        -frames:v 1 -vf "scale=320:-1" -q:v 10 \
        -y "$THUMB_PATH" -loglevel error 2>/dev/null; then
    echo "FRAME_FAIL: ffmpeg error during low-res extraction at ${TIMESTAMP}s"
    exit 1
fi

if [[ ! -f "$THUMB_PATH" || ! -s "$THUMB_PATH" ]]; then
    echo "FRAME_FAIL: no frame at ${TIMESTAMP}s (seek past end of video?)"
    exit 2
fi

if [[ "$LOW_RES_ONLY" == "--low-res-only" ]]; then
    echo "FRAME_OK_LOWRES: $THUMB_PATH"
    exit 0
fi

# Pass 2: full-res
if ! ffmpeg -ss "$TIMESTAMP" -i "$VIDEO_FILE" \
        -frames:v 1 -q:v 2 \
        -y "$OUTPUT_PATH" -loglevel error 2>/dev/null; then
    echo "FRAME_FAIL: ffmpeg error during full-res extraction at ${TIMESTAMP}s"
    exit 1
fi

if [[ ! -f "$OUTPUT_PATH" || ! -s "$OUTPUT_PATH" ]]; then
    echo "FRAME_FAIL: full-res extraction produced empty file"
    exit 1
fi

echo "FRAME_OK: $OUTPUT_PATH (thumb: $THUMB_PATH)"
