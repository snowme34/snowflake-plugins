# adversarial-review

Adversarially review anything — code, a document, a design, a config, a prompt, a schema. Finds what's wrong with it instead of summarizing it.

## What it does

Works out how to actually run the target once, then launches one **independent subagent per round**, in parallel, each carrying a deliberately **opposing** bias:

| Round | Bias | Asks |
|-------|------|------|
| 1 | Preserve correctness | Where does it break? Every "I validate X" claim gets an X-bypassing input, actually run. |
| 2 | **Delete** | What earns its existence? Default answer: remove it. |
| 3 | **Distrust the premise** | Does the test assert *should*-behavior or merely *current* behavior? Is the fixture itself a lie? |
| 4 | **Use it** | Names, errors, and return values are UI — review them as UI. |
| 5 | **Assume hostile input** | Real payloads, actually fired. Concrete payload → concrete thing obtained. |

Rounds that don't fit the target are skipped, not padded. A clean round gets one line.

## Why opposing biases

Opposition is the only real source of diversity — lenses pointing the same direction restate one finding in several wordings. In the author's own use, four rounds all biased toward *preserve correctness* surfaced no redundancy at all; a single round biased toward *delete* surfaced twelve.

Two rules do most of the work:

- **Round 2 may not rank by severity.** Redundant code never *hurts* — sort by harm and it sinks to the bottom, and nothing ever gets deleted. The findings are grouped by round in the final report for the same reason: collapsing everything into one severity ranking buries every round that isn't Round 1.
- **Tests are suspect #1.** A test can weld a bug into "correct behavior" and stay green forever. Green ≠ correct; it only proves the code matches the assumptions you wrote down, not that those assumptions are right.

## How it differs from the built-in reviewers

`/code-review`, `/security-review`, and PR-review toolkits are bound to a diff and sort everything into critical / important / nice-to-have. Two consequences: they can't review a spec, a prompt, or a design, and their "nice to have" bucket is where deletions and misleading names go to die. This skill takes any artifact and refuses the merge.

## Usage

Say "adversarially review `<target>`", "red-team this", "poke holes in this", or "what am I missing here?".

Findings come back grouped by round, each marked **confirmed** (verified) or **disputed** (the driving agent thinks the subagent overreached) — adversarial agents overreach, so the output is filtered, not forwarded. **Open questions** are listed separately: assumptions no agent can settle, only you can.

## Skills

- `adversarial-review` — the review harness
