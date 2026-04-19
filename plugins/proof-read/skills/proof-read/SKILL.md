---
name: proof-read
description: Proofread a markdown document in four passes, editing the file directly. Use when the user asks to proofread, review, or check a markdown document — blog posts, stories, notes, or any prose.
triggers:
  - proofread
  - proof read
  - proof-read
  - review document
  - check my writing
---

# Proof Read

Proofread a markdown document in four passes, editing the file directly. Maintain a global counter for review numbers across the whole document (never reset per section).

**Passes are organized by scope, not type:**

| Pass | Scope | Action |
|------|-------|--------|
| 1 | Mechanical — typos & formatting | Auto-fix silently |
| 2 | Mechanical — grammar & syntax | Auto-fix silently |
| 3 | Sentence / paragraph level | Insert `<review pass="3">` tag |
| 4 | Section & document level | Insert `<review pass="4">` tag |

All Pass 3 and Pass 4 comments use the same tag format:

```
<review remove-to-apply pass="N" id="M"> [comment]</review>
```

---

## Pass 1 — Typos & Formatting (auto-fix, silent)

*Typos:*
- Misspelled words (`teh` → `the`, `recieve` → `receive`)
- Missing or doubled punctuation (`..` → `.`)
- Smart-quote / apostrophe consistency if already established in the document

*Capitalization:*
- Wrong capitalization at sentence start
- Heading capitalization — follow the pattern already established in the document (title case or sentence case; never mix)
- List items — capitalize consistently (all start with a capital, or none do; follow existing pattern)

*Line breaks & spacing:*
- Missing blank line before and after headings, code blocks, and block quotes
- Missing blank line between list and surrounding prose
- Multiple consecutive blank lines → collapse to one
- Trailing spaces on lines
- Consistent punctuation at end of list items (all items end with `.`, or none do; follow existing pattern)

## Pass 2 — Grammar & Syntax (auto-fix, silent)

- Subject-verb agreement
- Wrong tense (when clearly unintentional)
- Missing articles (`a`, `an`, `the`) when the sentence breaks without one
- Run-on sentences — split with a period or semicolon, not a comma splice
- Code blocks: fix **syntax and formatting only** (indentation, unclosed brackets, missing colons, wrong quote style). **Never fix logic or change behavior.** Code may be intentionally broken to demonstrate a bug.

## Pass 3 — Sentence / Paragraph Level

Do not auto-edit. Insert a `<review remove-to-apply pass="3" id="N">` tag on a new line immediately after the problematic line or paragraph.

Covers both **correctness problems** (things wrong or broken as written) and **improvement suggestions** (things fine but could be stronger). Always include a concrete suggested fix or rewrite.

Correctness problems:
- Ambiguous or unclear meaning
- Contradictory or inconsistent statements
- Unclear pronoun reference
- Logic errors (invalid inference, false causation, non-sequitur, circular reasoning)
- Factual-looking claims that appear wrong
- Missing context that makes the sentence unintelligible without it

Improvement suggestions — always provide a concrete rewrite:
- *Conciseness* — wordy phrases (`in order to` → `to`), redundant qualifiers (`very unique`), throat-clearing openers (`It should be noted that...` → cut), sentences that say the same thing twice
- *Naturalness & idiom* — stiff or unnatural phrasing replaced with how a fluent writer would say it
- *Precision & persuasion* — vague or weak word choices (`good`, `fast`, `important`) replaced with specific, convincing language
- *Fluency* — sentences that are grammatically correct but awkward to read aloud
- *Sentence-level completeness* — a claim that needs a brief example, qualifier, or definition to be credible

Example:

```markdown
We disabled caching, so the server became faster.
<review remove-to-apply pass="3" id="1"> Logic error — disabling caching typically increases load. Verify the causal claim or reverse it.</review>

This is a very unique and interesting approach that has many good benefits.
<review remove-to-apply pass="3" id="2"> Wordy and vague — suggest: "This approach has one key advantage: [name it]."</review>
```

## Pass 4 — Section & Document Level

Read the entire document as a whole. Approach this as a professor grading a student's essay — evaluate the writing as a complete piece, not sentence by sentence.

**Before inserting any tags, assess the document through the SOAPSTone lens:**

- **Speaker**: Who is the author? Is their voice and persona consistent throughout?
- **Occasion**: What is the context or trigger for this piece? Is it made clear?
- **Audience**: Who is the intended reader? Does the writing calibrate appropriately to them?
- **Purpose**: What is the document trying to accomplish? Does every section serve that purpose?
- **Subject**: Is the subject clearly defined and consistently maintained?
- **Tone**: Is the tone consistent, appropriate to the audience and purpose, and free of unintended register shifts?

Then evaluate:

- **Argument & logic**: Is there a clear thesis or central claim? Does the evidence support it? Are there unsupported leaps, missing warrants, or logical gaps?
- **Organization & flow**: Does the document have a coherent structure? Do sections follow a logical order? Are transitions present and smooth?
- **Completeness**: Are there obvious gaps — missing context, unaddressed counterarguments, sections that need examples?
- **Proportion**: Is each section given appropriate weight relative to its importance? Too much padding somewhere? A key point underdeveloped?

Insert `<review remove-to-apply pass="4" id="N">` only. Tag placement:

| Scope | Where to insert |
|-------|----------------|
| Whole section | After the last line of that section, before the next `##` heading |
| Whole document | At the very end of the file, after all other content |

Prefix the tag body with `[Section]` or `[Document]` to make scope clear.

Example:

```markdown
## Conclusion

We should adopt this approach.

<review remove-to-apply pass="4" id="5"> [Section] The conclusion restates the recommendation but never synthesizes the argument. Add 1–2 sentences connecting back to the central problem from the introduction.</review>

<review remove-to-apply pass="4" id="6"> [Document] Tone shifts between casual ("just do this") and formal ("one must consider") across sections. Pick one register and apply it consistently.</review>
```

## Rules

| Situation | Pass | Action |
|-----------|------|--------|
| Obvious typo | 1 | Auto-fix |
| Capitalization, line breaks, spacing, list punctuation consistency | 1 | Auto-fix |
| Clear grammar error | 2 | Auto-fix |
| Code logic / intentional bug | — | Leave untouched |
| Correctness problem at sentence level | 3 | `<review remove-to-apply pass="3" id="N">` after the line |
| Sentence-level improvement (conciseness, idiom, precision, fluency) | 3 | `<review remove-to-apply pass="3" id="N">` after the line |
| Structural or rhetorical issue at section level | 4 | `<review remove-to-apply pass="4" id="N">` at end of section |
| Argument, flow, tone, or audience issue at document level | 4 | `<review remove-to-apply pass="4" id="N">` at end of file |

## Output Summary

After editing, print:
- N typos & formatting fixes
- N grammar fixes
- N Pass 3 comments (list each by ID with a one-line description)
- N Pass 4 comments (list each by ID with a one-line description, noting scope: section / document)

If the document is clean on any category, say so briefly.

Then tell the user:

> To approve a change: remove the `remove-to-apply` attribute from its tag (e.g. `<review remove-to-apply pass="3" id="1">` → `<review pass="3" id="1">`), then say **"apply approved tags"**.

## Applying Approved Tags

When the user says "apply approved tags" (or similar), scan the document for `<review>` tags **without** the `remove-to-apply` attribute. For each one, use the `pass` attribute to determine how to apply it:

- **`pass="3"` tag** (sits immediately after a specific line): apply the fix to that line, then delete the tag.
- **`pass="4"` tag with `[Section]`** (sits at the end of a section): rewrite or add content within that section as described, then delete the tag.
- **`pass="4"` tag with `[Document]`** (sits at the end of the file): apply the change globally or add the missing content where appropriate, then delete the tag.

Leave all tags that still have `remove-to-apply` completely untouched.
