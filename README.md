# snowflake-plugins

Claude Code plugins by [snowme34](https://github.com/snowme34).

```shell
/plugin marketplace add snowme34/snowflake-plugins
```

## Plugins

| Plugin | Description |
|--------|-------------|
| [proof-read](#proof-read) | Proofread markdown in four passes |
| [learn-everything](#learn-everything) | Any video, audio, or text → structured learning notes |

---

### proof-read

Proofread a markdown document in four passes: silently fix typos and grammar, then annotate sentence- and document-level issues with inline review tags. [→ README](plugins/proof-read/README.md)

```shell
/plugin install proof-read@snowflake-plugins
```

### learn-everything

Turn any video, audio, or text into structured learning notes — semantic chapters, verbatim quotes anchored to exact timestamps, and active-recall questions. Transcription runs on the Metal GPU on Apple Silicon and transcribes chunks in parallel, which is worth roughly 8x over the naive single-process CPU path. [→ README](plugins/learn-everything/README.md)

```shell
/plugin install learn-everything@snowflake-plugins
```

Run `/video-dl-setup` once before first use. Requires `ffmpeg`.
