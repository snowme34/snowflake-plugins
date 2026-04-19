# proof-read

Proofread a markdown document in four passes, editing the file directly.

## What it does

| Pass | Scope | Action |
|------|-------|--------|
| 1 | Typos & formatting | Auto-fix silently |
| 2 | Grammar & syntax | Auto-fix silently |
| 3 | Sentence / paragraph level | Insert annotated `<review>` tags |
| 4 | Section & document level | Insert annotated `<review>` tags |

Pass 3 and 4 suggestions are non-destructive — they use `<review remove-to-apply>` tags so you can review and selectively approve changes before they're applied.

## Usage

Say "proofread `<file>`" or "proof-read `<file>`" to invoke the skill.

After the review, remove the `remove-to-apply` attribute from tags you want applied, then say **"apply approved tags"**.

## Skills

- `proof-read` — the main proofreading workflow
