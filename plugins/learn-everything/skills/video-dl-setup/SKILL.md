---
name: video-dl-setup
description: >
  One-time setup for video transcription and download tools. Creates a shared Python venv,
  installs faster-whisper and yt-dlp, and verifies ffmpeg is available.
allowed-tools: Bash
argument-hint: (no arguments needed)
effort: low
---

## Step 1: Check python3 (version >= 3.10 required)

The transcription scripts use `X | None` type syntax, which requires **Python 3.10+**.

```bash
python3 --version || { echo "python=missing"; exit 1; }
PYVER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
if python3 -c 'import sys; exit(0 if sys.version_info >= (3,10) else 1)'; then
  echo "python=ok ($PYVER)"
else
  echo "python=too-old ($PYVER, need 3.10+)"
fi
python3 -c "import venv" 2>&1 || echo "WARN: python3-venv may need installing — apt install python3-venv"
```

If output is `python=missing` or `python=too-old`, **STOP and ask the user to install Python 3.10+ themselves** (their preferred method — pyenv, python.org installer, distro package, etc.). **Do NOT auto-install Python** (e.g. via Homebrew/apt) — the user manages their own Python. Print this and wait:
> **Python 3.10+ required** (found: `<PYVER or none>`).
> Please install Python 3.10 or newer, then re-run this skill.
> If `python3` is not the version you want used, point me at the right interpreter.

## Step 2: Check ffmpeg

```bash
command -v ffmpeg >/dev/null 2>&1 && echo "ffmpeg=ok" || echo "ffmpeg=missing"
```

If output is `ffmpeg=missing`, print install instructions and stop:
> **ffmpeg not found.**
> - WSL/Ubuntu: `sudo apt-get install -y ffmpeg`
> - macOS: `brew install ffmpeg`

## Step 3: Create venv (skip if exists)

```bash
if [ -x ~/.claude/my-venvs/video-learn/bin/python ]; then
  echo "venv=exists (skipping)"
else
  mkdir -p ~/.claude/my-venvs
  python3 -m venv ~/.claude/my-venvs/video-learn
fi
```

## Step 4: Install deps

`mlx-whisper` runs Whisper on the Metal GPU and is several times faster than the CPU-only
`faster-whisper`. Install it on Apple Silicon; keep `faster-whisper` as the portable fallback.

```bash
~/.claude/my-venvs/video-learn/bin/pip install --upgrade pip --quiet
~/.claude/my-venvs/video-learn/bin/pip install faster-whisper yt-dlp || { echo "pip-install=failed"; exit 1; }
if [ "$(uname -s)" = "Darwin" ] && [ "$(uname -m)" = "arm64" ]; then
  ~/.claude/my-venvs/video-learn/bin/pip install mlx-whisper || echo "mlx-install=failed (will fall back to CPU)"
fi
```

## Step 5: Verify

```bash
~/.claude/my-venvs/video-learn/bin/python -c "import faster_whisper; print('faster_whisper=ok')"
~/.claude/my-venvs/video-learn/bin/python -c "import yt_dlp; print('yt_dlp=ok')"
~/.claude/my-venvs/video-learn/bin/python -c "import mlx_whisper; print('mlx_whisper=ok (GPU)')" 2>/dev/null \
  || echo "mlx_whisper=absent (CPU fallback)"
ffmpeg -version 2>&1 | head -1
```

## Step 6: Bilibili setup (optional)

Bilibili requires authentication cookies. If you need Bilibili support:

1. Log into bilibili.com in your browser
2. Install the "Get cookies.txt LOCALLY" browser extension
3. Export cookies in Netscape format
4. Save to: `~/.claude/my-auth/cookies-bilibili.txt`

Alternative (Chrome must be fully closed first):
```bash
~/.claude/my-venvs/video-learn/bin/yt-dlp --cookies-from-browser chrome "https://www.bilibili.com/video/BVxxxxxx"
```

Without cookies, all Bilibili downloads fail with HTTP 412.

## Step 7: Print status

```
Setup complete.
Venv: ~/.claude/my-venvs/video-learn/
mlx-whisper: ok (GPU)   # Apple Silicon only
faster-whisper: ok
yt-dlp: ok
ffmpeg: ok
```
