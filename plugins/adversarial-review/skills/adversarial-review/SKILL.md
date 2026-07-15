---
name: adversarial-review
description: >
  Adversarially review any target — code, a document, a design, a config, a prompt, a schema, a plan.
  Runs one independent subagent per round, each carrying an OPPOSING bias (hunt defects, delete,
  doubt the premise, be the consumer, be the attacker), demands executed evidence over speculation,
  and reports findings grouped by round instead of collapsing them into one severity ranking.
  Use whenever the user wants something torn apart rather than summarized — "review this",
  "find what's wrong", "poke holes in it", "red-team it", "self-review before I ship",
  "is this actually correct?", "what am I missing?", "am I over-engineering this?" — and
  proactively before shipping, merging, or publishing anything where a missed defect is expensive.
  Prefer it over a single-pass review, which restates one perspective and is structurally blind to
  everything that perspective cannot see. Unlike diff- and PR-oriented reviewers, this works on any
  artifact, not just code.
---

# Adversarial Review

Find what is **wrong** with the target. Do not summarize it. Do not say it looks good.

## 1. Scope it

Name the target and its boundary: what is in, what is out of bounds. If the user was vague, pick the narrowest thing they plausibly meant and say which.

## 2. Learn how to run it — once

Before dispatching anything, work out how to actually exercise the target: the entrypoint, the venv or build, a minimal real input. Write it down.

Every round below is built on executed evidence, and an agent that cannot run the target falls back to speculation — the exact failure this skill exists to prevent. Deriving the harness once and handing it to every round is not a violation of their independence: they must not see each other's *findings*, but they should all start from the same working command.

If the target genuinely cannot be run (a design doc, a spec, an unbuildable branch), say so here. Then the rounds run on reading alone and every finding lands in evidence tier 2.

## 3. Dispatch one subagent per round

Launch them with the Agent tool, **all in a single message so they run in parallel**. One agent running the rounds back-to-back rationalizes its own earlier conclusions and converges — which destroys the only thing that makes this work.

**A subagent does not inherit this file.** You must build each prompt. Use this template:

```
You are running ONE round of an adversarial review. Your bias is deliberately partial:
do not be fair-minded, do not summarize, do not report what is fine.

TARGET: <path / scope / what is out of bounds>
HOW TO RUN IT: <the command or harness you verified in step 2>
READ-ONLY: do not modify the target. Scratch files go under <scratch dir> only.

YOUR ROUND — <paste the round's full text from the skill, verbatim>

EVIDENCE
- Tier 1 (preferred): concrete input → concrete wrong result, actually executed.
- Tier 2 (must be labeled): structural risk, design debt, an unwritten assumption, a name that
  lies. Not reproducible — and precisely what kills you in six months. Format:
  "Not reproducible; basis: X." Never drop a finding just because you could not run it.
- Could not run something? Write "I could not run this." Never dress reasoning up as execution.

The other rounds belong to other agents; do only yours. Found nothing? Say so in one line.
Never invent a finding to fill out the structure.
```

Pick the rounds that fit the target's nature — skipping an irrelevant round is correct, padding it is not. Rounds 2, 3, and 4 apply to nearly anything. Round 1 needs something executable. Round 5 needs untrusted input.

## The rounds

Opposition is the only real source of diversity. Lenses pointing the same direction just restate one finding in several wordings — the bias in the prompt is what produces divergence, so do not soften it.

### Round 1 — Hunt defects (bias: preserve correctness)

**Wherever the target claims "I validate X", construct an input that bypasses X and run it.** Reading the code and reasoning about it does not count.

Start with **silent corruption** — no error raised, but the result is wrong, empty, or mislabeled. It is the most expensive class because nothing alerts anyone. Then: boundaries and empties, swallowed exceptions, server-side faults reported as user errors.

That list is a floor, not a checklist. Once it is clear, drop it and judge from the target's actual nature — a generic quality checklist anchors attention on standard items, and the real wound is usually not on the list.

### Round 2 — Necessity (bias: DELETE)

For every branch, field, call, and abstraction: what earns its existence? **The default answer is delete it.**

**Do not rank this round by severity.** Redundant code never *hurts*; sort by harm and it sinks to the bottom, and nothing is ever removed. The only test is: **does it beat doing nothing?**

Hunt: state pushed to a caller that already knows it; fallbacks that substitute a guess for a missing truth; derived fields that restate visible information; defenses for cases that cannot occur; computation and network calls whose results nobody consumes.

Reasonable-sounding justifications — *"for transparency"*, *"best-effort"*, *"approximate"*, *"good enough"* — are camouflage, not reasons.

### Round 3 — Doubt the premise (bias: DISTRUST)

A target can be flawless, self-consistent, and built on a false premise.

**Tests are suspect #1: a test can weld a bug into "correct behavior" and stay green forever.** For each one: does it assert the behavior that *should* hold, or merely the behavior that *currently* holds? **Is the fixture itself trustworthy — build a real input and feed it through rather than trusting it.** This is the highest-yield instruction in the skill: a plausible-looking fake fixture passes every review that only reads code.

Read the history — `git log`, changelog, prior versions. Dead designs survive in names, comments, and fields, contradicting present behavior.

Any assumption you cannot confirm from the material itself → **flag it for the human.** They know things no agent can see.

### Round 4 — Be the consumer (bias: USE IT)

Who consumes this — a person, a model, another service?

**Everything a consumer reads directly — names, docstrings, error messages, return values, defaults — is UI. Review it as UI, not as code.**

Then use the target end to end for its real purpose. Where were you misled? Where did you do wasted work? Did a name lie to you?

### Round 5 — Be the attacker (bias: ASSUME HOSTILE INPUT)

Your question is not *"does normal input break it?"* but *"what do I get if I feed it malice on purpose?"*

**State your threat model first:** who is the attacker, what do they control, what are they after. If the target has no untrusted input, say so in one line and stop.

Behind every untrusted entry point — request body, header, token, file, argument, URL, filename — stands someone who wants to hurt you. **Build real payloads and fire them.**

- Authn/authz bypass: forged, tampered, or replayed tokens; privilege escalation; timing side channels
- Injection: command, SQL, path traversal, SSRF, template/log injection, decompression bomb, XXE
- Resource exhaustion: a tiny input that blows up memory, CPU, disk, or file handles
- Leakage: tokens, paths, internal identities escaping through errors, logs, or return values
- Trust-boundary confusion: external input used as though it were trusted

Every finding: **concrete payload → concrete thing obtained.**

## 4. Verify before you report

Do not forward the subagents' output wholesale — adversarial agents overreach and argue from theory. Re-run the tier-1 claims that would change what the human does; take tier-2 findings on the strength of their argument. Mark each finding **confirmed** or **disputed (why)**.

## 5. Report

**Group by round.** Do not merge the rounds into a single severity ranking: severity is Round 1's ruler, and applying it to everything buries Round 2 and Round 4 at the bottom, where nothing is ever deleted or renamed. That is manufacturing diversity and then throwing it away. Rank freely *within* a round.

The one thing that outranks grouping: if something is critical — an exploit, data loss, silent corruption in production — lead with it as a single line before the rounds, then list it again in its own round. Nobody should have to read to Round 5 to find the RCE.

Then:
- A clean round gets **one line and no heading**. A skipped round gets one line saying why.
- **Open questions** go last, listed separately: the Round 3 assumptions only the human can settle.
- Deliver problems, not comfort.
