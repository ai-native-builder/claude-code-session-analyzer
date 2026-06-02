---
title: Are You Actually Using Claude Code Well? I Built a Free Scorer Based on Anthropic's Own Research
published: false
tags: ai, claudecode, productivity, opensource
canonical_url: https://www.ai-native-builder.com/claude-code-maturity-score
cover_image:
---

Most developers using Claude Code have no idea whether they're doing it well or not. You can feel productive — but productive and *effective* aren't the same thing. You might be over-steering on every session, delegating the wrong kinds of tasks, or letting Claude run without meaningful oversight. The problem is there's been no way to measure it.

Until Anthropic published the data.

In late 2025, Anthropic released [*How AI Is Transforming Work at Anthropic*](https://www.anthropic.com/research/how-ai-is-transforming-work-at-anthropic) — a study of 132 engineers, 53 interviews, and 200,000 Claude Code session transcripts spanning February to August 2025. It's one of the most concrete datasets on what high-quality AI collaboration actually looks like in practice.

I used that data to build a free tool: **[Claude Code Session Analyzer](https://www.ai-native-builder.com/analyze/claude-code)**. Upload your `.jsonl` session files, pick an AI provider, and get a behavioral score across 6 dimensions — benchmarked directly against the Anthropic engineering cohort.

This post explains the methodology, how the scoring works technically, and what the numbers actually mean.

---

## What the Anthropic Data Shows

Before getting into the tool, it's worth understanding what Anthropic actually found — because these numbers are the foundation of every score the analyzer produces.

Between February and August 2025, the median Anthropic engineer went from:

| Metric | Feb 2025 | Aug 2025 | Change |
|---|---|---|---|
| Max consecutive tool calls | 9.8 | 21.2 | +116% |
| Avg human turns per session | 6.2 | 4.1 | −34% |
| Avg task complexity (1–5) | 3.2 | 3.8 | +19% |

The pattern is clear: better engineers are giving Claude more autonomy (longer uninterrupted tool chains), steering less (fewer human turns), and tackling harder problems over time.

The study also found that 27% of Claude-assisted work was "new work" — tasks that simply wouldn't have been done without AI. That's not replacing existing work, it's expanding the surface area of what gets shipped.

These aren't arbitrary benchmarks. They're what the February-to-August shift looked like in a cohort of engineers actively getting better at AI collaboration.

---

## The 6 Dimensions

The analyzer scores your sessions across six dimensions. Here's what each one measures and why it matters.

### 1. [Delegation Intelligence](https://www.ai-native-builder.com/claude-code-maturity-score/delegation-intelligence) — 25%

The highest-weighted dimension, because task selection cascades into everything else.

**What it measures:** Are you delegating tasks that are actually well-suited to Claude? The Anthropic study identified that high performers choose tasks that are "easily verifiable, well-defined, repetitive, or outside their expertise." Architectural decisions with no constraints score poorly. Debugging a specific failure, refactoring a defined module, or writing test fixtures score well.

**How it's scored:** Sessions are classified by task type (`debugging`, `feature_implementation`, `refactoring`, `code_understanding`, `design_planning`, `data_science`, `front_end`, `papercut_fix`) and appropriateness (`good`, `poor`, `unclear`). A good delegation is one where appropriateness = "good" and complexity ≤ 3, or the task type is inherently well-suited to AI delegation.

```
score = (good_delegations / total_sessions) × 10
```

### 2. [Autonomy Calibration](https://www.ai-native-builder.com/claude-code-maturity-score/autonomy-calibration) — 20%

**What it measures:** How much uninterrupted space you give Claude to work. The key metric is the ratio of average max consecutive tool calls to average human turns per session.

The Feb → Aug shift from 9.8 to 21.2 consecutive tool calls is the clearest signal in the entire dataset. Engineers who improved the most stopped interrupting mid-task.

**How it's scored:** The ratio maps to a 1–10 scale anchored to the Anthropic benchmarks:

```
ratio = avgMaxConsecutiveToolCalls / avgHumanTurns

≥ 5.17  → 10   (Aug 2025 best practice: 21.2 / 4.1)
1.58    →  6   (Feb 2025 baseline:       9.8  / 6.2)
< 0.2   →  1
```

### 3. [Oversight Quality](https://www.ai-native-builder.com/claude-code-maturity-score/oversight-quality) — 20%

**What it measures:** Whether you're catching and correcting bad outputs — but not over-correcting. This follows an inverted-U curve. Too little oversight means passive rubber-stamping. Too much means micromanaging, which correlates with not granting autonomy in the first place.

The optimal correction/redirection rate is **10–30% of turns**, peaking at 20%.

**How it's scored:**

```
oversightRate = (correction + redirection events) / total turns

10–30%  →  8–10  (optimal, peak at 20% = 10)
< 5%    →  1–4   (passive, not verifying)
> 50%   →  1–4   (micromanaging)
```

Oversight events are detected by the LLM classifier, with keyword heuristics (`"wrong"`, `"actually"`, `"undo"`, `"don't"`, etc.) as a fallback.

### 4. [Complexity Progression](https://www.ai-native-builder.com/claude-code-maturity-score/complexity-progression) — 15%

**What it measures:** Whether you're tackling harder problems over time. A flat or declining complexity curve suggests you've found a comfort zone and stopped pushing.

The Anthropic cohort averaged a complexity increase from 3.2 → 3.8 over 6 months — roughly a slope of 0.024 per session.

**How it's scored:** Linear regression on complexity scores (1–5) ordered by session date. Slope ≥ 0.024 maps to 8+; flat maps to 5; declining maps to 1–4.

### 5. [Task Breadth](https://www.ai-native-builder.com/claude-code-maturity-score/task-breadth) — 10%

**What it measures:** How many distinct task types you delegate. The study found that high performers became more "full-stack" — using Claude across debugging, front-end, data science, and writing, not just one lane.

**How it's scored:** There are 8 task types (excluding `other`). Score = (distinct types / 8) × 10.

### 6. [New Work Generation](https://www.ai-native-builder.com/claude-code-maturity-score/new-work-generation) — 10%

**What it measures:** What percentage of your sessions are tasks that simply wouldn't exist without AI — papercuts, exploratory work, nice-to-haves that never made the backlog. The Anthropic benchmark is 27%.

**How it's scored:** `is_new_work` is classified by the LLM. Score maps linearly from 0% (score = 1) to 27% (score = 7) to 40%+ (score = 10).

---

## How It Works Under the Hood

The analyzer is a single `index.html` file — no server, no install, no data leaving your machine except what's explicitly sent to the AI provider.

Here's the full pipeline:

### Step 1 — Parse the JSONL files locally

Claude Code stores every session at `~/.claude/projects/<project>/<session-id>.jsonl`. Each line is one event. The parser reads all files, groups by `sessionId`, and identifies real human turns vs. API artifacts.

The key distinction: `tool_result` entries have `role: user` in the raw data but are not human input — they're Claude's tool outputs being returned to the API. The parser only counts a turn as human when `content` contains at least one non-empty `text` block.

It also strips injected context from human messages before analysis: `<ide_opened_file>`, `<system-reminder>`, and `<ide_selection>` tags are removed so they don't pollute the task classification.

### Step 2 — Compute structural metrics (no API call)

For every session, before making any API calls:

- `totalTurns` — real human turn count
- `maxConsecutiveToolCalls` — longest uninterrupted tool chain before a human turn resets the counter
- `correctionCount` — keyword-based heuristic count
- `sessionStart` — first timestamp, used for complexity progression ordering
- `taskTextSummary` — first 2 + last human message, capped at 1200 characters

This step processes all sessions, even if there are more than 100. The 100-session cap only applies to LLM calls.

### Step 3 — Three LLM API calls

Sessions are batched in groups of 5 for all three calls.

**Call 1 — Session classification.** Input: `taskTextSummary`, `totalTurns`, `maxConsecutiveToolCalls`. Output per session: `task_type`, `complexity (1–5)`, `is_new_work`, `delegation_appropriateness`.

**Call 2 — Oversight event detection.** Input: up to 20 human turns per session, each capped at 150 characters. Output: each turn labelled as `correction`, `redirection`, `validation`, or `pure_input`.

**Call 3 — Holistic summary.** Input: aggregated metrics and all 6 dimension scores. Output: 3 strengths, 3 gaps with recommendations, delegation pattern description, maturity narrative.

If the LLM returns no oversight events for a session, the keyword heuristic count is used as a fallback.

### Step 4 — Score and render

All six dimension scores are computed from the classified data, combined into an overall score, and mapped to a maturity label:

| Score | Label |
|---|---|
| 1–3 | Early Adopter |
| 4–5 | Developing Collaborator |
| 6–7 | Effective Delegator |
| 8–9 | AI-Native Builder |
| 10 | AI Power User |

---

## Privacy

The only data that leaves your machine:

- First 2 + last user message per session (capped at 1200 chars)
- Turn counts and tool call counts
- Aggregated scores in the final summary call

Full conversation content, code, file paths, and assistant responses are never sent anywhere. All parsing and metric computation happens in the browser.

---

## Try It / Run It Yourself

**Hosted version (free, no sign-in):** [ai-native-builder.com/analyze/claude-code](https://www.ai-native-builder.com/analyze/claude-code)

**Run it locally:** Clone [the repo](https://github.com/ai-native-builder/claude-code-session-analyzer) and open `index.html` in any browser. No install, no build step.

**Self-host:** Drop `index.html` on any static host (GitHub Pages, Netlify, S3). Users bring their own API key. If you want the key server-side, replace the `callAPI()` function with a call to your own backend route.

The tool supports Gemini (`gemini-3.1-flash-lite`, cheapest), OpenAI (`gpt-4o-mini`), or Claude (`claude-sonnet-4-6`). A full analysis of 100 sessions costs less than $0.10 with any of these.

---

## What to Do With Your Score

The score is most useful as a gap identifier, not a ranking. The dimension breakdown tells you specifically where to focus:

- **Low Delegation Intelligence** → audit what you're asking Claude to do. If you're using it for architectural decisions or work with no clear success criteria, that's where to start.
- **Low Autonomy Calibration** → try longer sessions without interrupting. Set a task, step away, review the output. The Feb → Aug improvement was largely engineers learning to trust longer chains.
- **Low Oversight Quality (too low)** → build a habit of explicit verification. Read outputs, run the code, check the diff.
- **Low Oversight Quality (too high)** → you're correcting so often it suggests either task selection or instructions aren't working. Fix upstream.
- **Flat Complexity Progression** → deliberately push harder tasks into Claude. The growth in the Anthropic cohort came from engineers actively expanding what they attempted.

The full methodology — every formula, every benchmark reference, every score mapping — is in [METHODOLOGY.md](https://github.com/ai-native-builder/claude-code-session-analyzer/blob/main/METHODOLOGY.md).

---

The Anthropic data is rare: a large, real-world dataset on what getting better at AI collaboration actually looks like over time. This tool is an attempt to make those benchmarks useful for individual developers rather than just an interesting read.

If you find it useful, the [repo is open source](https://github.com/ai-native-builder/claude-code-session-analyzer) — PRs welcome, especially for improving the LLM classification prompts.
