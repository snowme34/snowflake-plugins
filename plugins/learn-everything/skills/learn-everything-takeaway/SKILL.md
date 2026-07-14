---
name: learn-everything-takeaway
description: >
  Generates human-style learning notes from any single piece of content — a book,
  video, blog post, article, online course, or any passage of text/image input.
  Optimized for retention, not just summary: every note ends with active-recall
  prompts so the reader rebuilds the idea instead of re-reading it.
allowed-tools: Bash Read WebSearch
argument-hint: <report-path-or-text> [--type how-to|concept|interview|news|lecture] [--questions "Q1; Q2"] [--output PATH]
effort: medium
---

Input: $ARGUMENTS

## Core principle

A summary the reader skims teaches almost nothing; passive re-reading is the weakest
form of study. The job of this skill is not to compress the source — it is to make the
reader able to *reconstruct* its load-bearing idea later, unaided. Two consequences run
through every step below:

- **Mechanism over checklist.** The reader must understand *why* the framework works,
  not just what its steps are. One mental model that makes the steps obvious beats a
  flat list of steps.
- **Retrieval over recognition.** End every note with active-recall prompts (Step 6).
  A note the reader can nod along to has failed; a note that makes them stop and answer
  has worked.

## Step 0: Parse arguments

- `INPUT` — file path, raw text, or image file path(s)
- `--type TYPE` — content type override (optional)
- `--questions TEXT` — semicolon-separated questions to answer
- `--output PATH` — override default output path (`./tmp-claude/learn-takeaway/takeaway.md`)

## Step 1: Load content

- `.md`, `.txt` → Read tool
- Image files → vision analysis
- Raw text → use directly

## Step 2: Locate the reader before writing (two questions)

Before writing anything, answer these two for yourself — they decide what the note keeps
and what it drops:

1. **What kind of content is this?** Is it teaching a *method* (how-to), explaining a
   *concept* (what/why), arguing a *claim* (interview/lecture), or reporting *events*
   (news)? Use `--type` if provided; otherwise infer from the table below.
2. **What is the single thing the reader must walk away able to do or explain?** This
   becomes the 一句话总结 and the spine of the note. Everything that doesn't serve it is
   a candidate for cutting.

| Type | Detection signals | Takeaway focus |
|---|---|---|
| how-to | tutorial structure, numbered steps, actionable advice | One mental model that makes the steps obvious. Steps follow. What can go wrong. When this doesn't apply. |
| concept | "explain", "what is", definition-heavy content | What it is. Core principles (3–5). Common misconceptions. One worked example. |
| interview | Conversational exchange, two or more voices | Main thesis per speaker. Key claims. Agreement/disagreement. One surprising insight. |
| news | Reporter tone, who/what/when/where | Who · What · When · Where · Why · What happens next |
| lecture | Dense structured info, single authoritative voice | Core thesis. Key concepts with definitions. How they connect. |
| default | Doesn't fit above | Key insights. Supporting evidence. What this changes about how you think. |

If `--questions` provided: answer each explicitly first, then add mode-appropriate notes.

## Step 3: Load reference example

Read `${CLAUDE_SKILL_DIR}/examples/{TYPE}.md`. If the file does not exist, skip this step.
It is a deliberately thin worked example: the `<!-- -->` annotations are the point — each
names the transferable principle behind its section. Take the principles, not the topic.
Quality target, not template.

## Step 4: Decide whether the idea has *shape*

Some ideas are linear prose; some have structure — a process with stages, a comparison
across dimensions, a hierarchy, a feedback loop, a relationship between parts. **When the
load-bearing mechanism has shape, draw it** (Step 5 template includes a `结构图` slot):
a small mermaid diagram, a markdown table, or an ASCII sketch carries that structure
further than a paragraph ever will, and a picture is far more retrievable than prose.

Guardrails so this stays useful and not decorative:
- No structure → no diagram. Pure procedure, definitions, and linear narration get prose. A diagram that isn't carrying the mechanism is decoration, and decoration trains the reader to skim.
- One diagram per note, maximum, unless the source genuinely has two independent structures.
- The diagram shows the *relationship*, not every detail. Detail lives in the prose around it.
- Source images: still embed a source frame/figure where it clarifies a specific point. That is separate from the structure diagram you draw yourself.

## Step 5: Write takeaway notes

Save to OUTPUT_PATH AND print to chat.

```markdown
## Takeaway: {TITLE or source description}

**一句话总结：** {The single most important thing the reader must walk away able to explain. One sentence, one thesis, no em-dashes, no semicolons — drop any clause that doesn't carry the load-bearing claim.}

### Answers to your questions
{Only if --questions provided.}

### 核心机制（为什么有效）
{One paragraph. The single insight that makes everything else follow. This is the mental model — if the reader gets only this, the steps/claims should feel obvious.}

### 结构图
{Only if the mechanism has shape (Step 4). A mermaid diagram, markdown table, or ASCII sketch of the relationship/process/comparison. Omit this entire section for linear content.}

### 最值得记住的句子
{1–2 verbatim quotes from source that crystallize the mechanism, plus the 1–2 most vivid metaphors verbatim — metaphors are the single most retrievable pieces. No commentary.}

### {Mode-appropriate sections}
{Steps, principles, claims — as relevant. Every number/name/threshold must trace to a verbatim quote.}

### 自测（主动回忆）
{3–5 questions, placed last. See Step 6. Each question followed by its answer.}
```

After drafting, proceed to Step 6 and Step 7.

## Step 6: Active recall — the retention layer

This is what separates a learning note from a summary. Write 3–5 questions that force the
reader to *reconstruct* the content, not recognize it. Put them last. List each answer
directly under its question, so the reader can self-check after attempting.

Rules for good recall questions:
- **Test the mechanism, not trivia.** "Why does {core mechanism} work?" beats "What year was X published?" Aim every question at the 一句话总结 and 核心机制 first; key numbers/thresholds second; never at incidental detail.
- **Prefer generative prompts:** "Explain {X} in one sentence." / "Predict what happens if {parameter} → 0." / "Give your own example of {principle}." / "When would this framework *fail*?" These beat yes/no or fill-in-the-blank, which test recognition.
- **Format** — question then answer, the answer traceable to the note above:

```markdown
**问题 1：{question}**
{answer}

**问题 2：{question}**
{answer}
```

- If `--questions` were provided, the recall set is *in addition* to answering them — don't substitute one for the other.

## Step 7: Critical Assessment

Identify the single load-bearing assumption the source hides — the one premise that, if
false, breaks the whole framework. Pressure-test that one.

Skip surface disclaimers (commercial intent, "results vary", one-sided framing) unless
they materially compromise the content. If nothing substantial to flag, omit.

Limit: 1–3 web searches, only when verification would change the evaluation.

**Output:** `## 批判性评估` in Chinese, 3–5 sentences:
- 最关键的隐藏假设 (the load-bearing premise)
- 在什么条件下框架会失效 (when it breaks)
- 来源可信度的一句话判断 (one-line source credibility)

## Rules

- Write all output in Simplified Chinese (简体中文)
- Every number, name, and timeline in the takeaway MUST be traceable to a verbatim quote. If you cannot cite it, drop it.
- No generic observations ("this video explains X clearly" is not a learning note)
- Capture the 1–2 most vivid metaphors verbatim — these are the most retrievable pieces
- Mental model over checklist — reader must understand *why* the framework works
- Active recall is mandatory, not optional — a note without Step 6 questions is a summary, and summaries don't stick
- Diagram only when the idea has shape (Step 4); no structure → prose. Never decorate.
- If the source doesn't explain its own mechanism (e.g. sales preview, syllabus name-dropping), say so plainly and keep the takeaway short. Do not pad. A short honest note beats a padded one.
- Know when you're done: once the 一句话总结, 核心机制, and 自测 cover the load-bearing idea, stop. Length is not the goal.
- If source has images/frames, embed them where they clarify a point