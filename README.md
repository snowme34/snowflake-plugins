# snowflake-plugins

Claude Code plugins by [snowme34](https://github.com/snowme34).

## Install

Inside a Claude Code session, add the marketplace once, then install the plugins you want:

```
/plugin marketplace add https://github.com/snowme34/snowflake-plugins
/plugin install learn-everything@snowflake-plugins
/plugin install proof-read@snowflake-plugins
/plugin install adversarial-review@snowflake-plugins
```

Prefer the terminal? The same steps as CLI commands:

```bash
claude plugin marketplace add https://github.com/snowme34/snowflake-plugins
claude plugin install learn-everything@snowflake-plugins
claude plugin install proof-read@snowflake-plugins
claude plugin install adversarial-review@snowflake-plugins
```

`learn-everything` needs `ffmpeg` on your PATH and a one-time setup — after installing, run
`/video-dl-setup` once. `proof-read` and `adversarial-review` need nothing extra.

## Plugins

| Plugin | Description |
|--------|-------------|
| [proof-read](#proof-read) | Proofread markdown in four passes |
| [learn-everything](#learn-everything) | Any video, audio, or text → structured learning notes |
| [adversarial-review](#adversarial-review) | Tear anything apart from five opposing angles |

---

### proof-read

Proofread a markdown document in four passes: silently fix typos and grammar, then annotate sentence- and document-level issues with inline review tags. [→ README](plugins/proof-read/README.md)

```
/plugin install proof-read@snowflake-plugins
```

### learn-everything

Turn any video, audio, or text into structured learning notes — semantic chapters, verbatim quotes anchored to exact timestamps, and active-recall questions. Transcription runs on the Metal GPU on Apple Silicon, several times faster than the CPU fallback. [→ README](plugins/learn-everything/README.md)

```
/plugin install learn-everything@snowflake-plugins
```

Run `/video-dl-setup` once before first use. Requires `ffmpeg`.

### adversarial-review

Review anything — code, docs, a design, a config — by launching one independent subagent per round, each carrying a deliberately **opposing** bias: hunt defects, delete, distrust the premise, be the consumer, be the attacker. Opposition is the only real source of diversity: four rounds all biased toward *preserve correctness* found 0 redundancies on a real target; one round biased toward *delete* found 12. Findings come back grouped by round, evidence-first, never re-sorted by severity. [→ README](plugins/adversarial-review/README.md)

```
/plugin install adversarial-review@snowflake-plugins
```
