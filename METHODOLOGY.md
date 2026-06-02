# How the Analyzer Works — Full Methodology

This document explains every step the analyzer takes from raw JSONL upload to final report score.

---

## 1. Input Data

Claude Code stores every session as a `.jsonl` file at:

```
~/.claude/projects/<project-name>/<session-id>.jsonl
```

Each line is one event. The relevant event types are:

| Event type | What it contains |
|---|---|
| `user` (with text block) | A real human message — prompt, instruction, correction |
| `user` (with tool_result) | Claude's tool output returned to the API — **not** a human turn |
| `assistant` (with tool_use) | Claude calling a tool (Bash, Edit, Read, etc.) |
| `assistant` (with text) | Claude's text response |
| `queue-operation` | System housekeeping — ignored |

**Key distinction:** `tool_result` entries have `role=user` in the raw data but are API artifacts, not human messages. The parser identifies a real human turn only when `content` contains at least one non-empty `text` block.

---

## 2. Parsing

The user uploads all `.jsonl` files from their project folder. The parser:

1. Reads all files line by line
2. Parses each line as JSON
3. Groups lines by `sessionId` field — one session = one `.jsonl` file, but multiple files are supported
4. Strips injected context blocks from user text: `<ide_opened_file>`, `<system-reminder>`, `<ide_selection>`

---

## 3. Structural Metrics (computed locally, no API)

For every session, these fields are computed directly from the raw data before any API call is made:

| Field | How computed | Used for |
|---|---|---|
| `totalTurns` | Count of entries where `type=user` AND content has a text block | Autonomy Calibration, Oversight Quality |
| `totalToolCalls` | Count of `type=tool_use` blocks across all assistant entries | Autonomy Calibration |
| `maxConsecutiveToolCalls` | Longest uninterrupted run of tool_use blocks before a human turn resets the counter | **Autonomy Calibration — key metric** |
| `correctionCount` | Human turns containing correction keywords (see below) | Oversight Quality fallback |
| `correctionRate` | `correctionCount / totalTurns` | Oversight Quality |
| `sessionStart` | First timestamp in the file (ISO string) | Complexity Progression ordering |
| `durationMinutes` | `(lastTimestamp − firstTimestamp) / 60000` | Complexity proxy |
| `taskTextSummary` | First 2 human messages + last human message, concatenated, capped at 1200 chars | Input to API Call 1 |
| `isPureChat` | `totalToolCalls === 0` | Excludes session from autonomy scoring |
| `isQuickQuery` | `totalTurns < 3` | Edge case flag |

**Correction keywords used for heuristic detection:**
`no `, `wrong`, `not that`, `don't`, `stop`, `wait`, `actually`, `instead`, `undo`, `revert`, `that's not`, `not right`, `incorrect`, `you missed`, `you forgot`

---

## 4. API Calls (3 total)

Sessions are sent to the chosen AI provider (Gemini, OpenAI, or Claude) in **batches of 5** to reduce total API calls and stay within rate limits.

If a project has more than 100 sessions, structural metrics are computed on all of them but LLM classification is run on a uniform sample of 100.

---

### API Call 1 — Per-Session Classification

**Input per session:** `taskTextSummary` + `totalTurns` + `maxConsecutiveToolCalls`

**Output per session:**

| Field | Type | What it means |
|---|---|---|
| `task_type` | enum | One of: `debugging`, `feature_implementation`, `refactoring`, `code_understanding`, `design_planning`, `data_science`, `front_end`, `papercut_fix`, `other` |
| `complexity` | integer 1–5 | 1 = basic edit/typo, 3 = standard feature, 5 = expert architecture |
| `is_new_work` | boolean | Would this task likely have been done without AI? |
| `delegation_appropriateness` | `good` / `poor` / `unclear` | Was this a well-chosen task to delegate to an AI assistant? |

---

### API Call 2 — Oversight Event Detection

**Input per session:** Up to 20 human turns, each capped at 150 characters

**Output per session:** Each turn classified as:

| Label | Meaning |
|---|---|
| `correction` | User correcting Claude's wrong output |
| `redirection` | User changing direction or scope |
| `validation` | User confirming Claude did it correctly |
| `pure_input` | New instructions, context, or questions |

`correction` + `redirection` events are summed to compute the refined oversight rate. If the LLM returns no events for a session, the keyword-based `correctionCount` is used as fallback.

---

### API Call 3 — Holistic Summary

**Input:** All session metadata + all 6 dimension scores + overall score

**Output:**
- 3 specific strengths drawn from the data
- 3 gaps with actionable recommendations
- A 1–2 sentence delegation pattern description
- A 2–3 sentence maturity narrative

---

## 5. The 6 Dimensions

### Dimension 1 — Delegation Intelligence (weight: 25%)

**What it measures:** Are the tasks being delegated to Claude the right ones?

**Formula:**
```
good_sessions = sessions where delegation_appropriateness = "good"
                AND (complexity ≤ 3 OR task_type ∈ {debugging, refactoring,
                     papercut_fix, code_understanding, data_science, front_end})

score = (good_sessions / total_sessions) × 10
```

**Benchmark:** Anthropic Work Study — good delegators choose tasks that are "easily verifiable, well-defined, repetitive, or outside their expertise."

**Score 1–10:** 0% good sessions = 1, 100% = 10, linear.

---

### Dimension 2 — Autonomy Calibration (weight: 20%)

**What it measures:** Does the user let Claude run autonomously, or do they over-steer?

**Formula:**
```
avgMaxConsec = average(maxConsecutiveToolCalls) across non-pure-chat sessions
avgTurns     = average(totalTurns) across all sessions
ratio        = avgMaxConsec / avgTurns
```

**Score mapping against Anthropic benchmarks:**

| Ratio | Score | Reference |
|---|---|---|
| ≥ 5.17 | 10 | Aug 2025 best practice (21.2 tool calls / 4.1 turns) |
| 4.0–5.17 | 9 | Near best practice |
| 3.0–4.0 | 8 | Strong autonomy |
| 2.5–3.0 | 7 | Good autonomy |
| 1.58–2.5 | 6 | At Feb 2025 baseline (9.8 / 6.2) |
| 1.2–1.58 | 5 | Below baseline |
| 0.8–1.2 | 4 | Heavy steering |
| 0.5–0.8 | 3 | Micro-managing |
| 0.2–0.5 | 2 | Very low autonomy |
| < 0.2 | 1 | Essentially manual |

---

### Dimension 3 — Oversight Quality (weight: 20%)

**What it measures:** Does the user catch and correct bad outputs? Optimal is neither too passive nor too reactive.

**Formula:**
```
oversightRate = (total correction + redirection events) / total turns
```

**Inverted-U scoring — optimal range is 10–30%, peak at 20%:**

| Rate | Score |
|---|---|
| 10–30% | 8–10 (peak at 20% = 10) |
| 5–10% | 5–7 (under-supervising) |
| < 5% | 1–4 (passive, no verification) |
| 30–50% | 5–7 (over-correcting) |
| > 50% | 1–4 (micro-managing) |

**Benchmark:** Anthropic Work Study — "most cannot fully delegate more than 0–20% of work; active supervision is the norm."

---

### Dimension 4 — Complexity Progression (weight: 15%)

**What it measures:** Is the user tackling increasingly complex tasks over time? A positive slope signals a learning curve.

**Formula:** Linear regression on complexity scores (1–5) ordered by `sessionStart` date.

```
slope = (n·Σxy − Σx·Σy) / (n·Σx² − (Σx)²)
```

**Score mapping:**

| Slope per session | Score | Meaning |
|---|---|---|
| ≥ 0.05 | 10 | Rapid complexity growth |
| 0.024–0.05 | 8 | At Anthropic benchmark rate (3.2 → 3.8 in ~25 sessions) |
| 0.01–0.024 | 7 | Gradual growth |
| 0–0.01 | 5 | Flat / stable |
| −0.01–0 | 4 | Slight decline |
| −0.024–−0.01 | 3 | Declining |
| < −0.024 | 1 | Strong decline |

**Benchmark:** Anthropic internal cohort — average task complexity grew from 3.2 → 3.8 over 6 months.

---

### Dimension 5 — Task Breadth (weight: 10%)

**What it measures:** How wide a range of task types is the user delegating? Full-stack breadth is a signal of confident, mature AI use.

**Formula:**
```
distinct_types = count of unique task_type values (excluding "other")
score = (distinct_types / 8) × 10
```

**The 8 task types (from Anthropic Work Study Fig 4):**
`debugging`, `feature_implementation`, `refactoring`, `code_understanding`, `design_planning`, `data_science`, `front_end`, `papercut_fix`

---

### Dimension 6 — New Work Generation (weight: 10%)

**What it measures:** What percentage of tasks are "AI-enabled" — things that wouldn't have been done without Claude (papercuts, exploratory work, nice-to-haves)?

**Formula:**
```
pct_new_work = sessions where is_new_work = true / total sessions
```

**Score mapping against Anthropic benchmark of 27%:**

| % new work | Score |
|---|---|
| ≥ 40% | 10 |
| 27–40% | 7–10 (linear) |
| 1–27% | 1–7 (linear) |
| 0% | 1 |

**Benchmark:** Anthropic Work Study — 27% of Claude-assisted work wouldn't have been done otherwise; 8.6% classified as papercut fixes.

---

## 6. Overall Score

```
overall = (Delegation Intelligence × 0.25)
        + (Autonomy Calibration    × 0.20)
        + (Oversight Quality       × 0.20)
        + (Complexity Progression  × 0.15)
        + (Task Breadth            × 0.10)
        + (New Work Generation     × 0.10)
```

---

## 7. Maturity Labels

| Score | Label | Description |
|---|---|---|
| 1–3 | Early Adopter | Simple tasks, heavy steering, limited delegation |
| 4–5 | Developing Collaborator | Growing delegation, some oversight, narrow task range |
| 6–7 | Effective Delegator | Strategic task choice, appropriate autonomy, decent breadth |
| 8–9 | AI-Native Builder | High autonomy, strong oversight, generating new work |
| 10 | AI Power User | Benchmark-beating across all dimensions |

---

## 8. Benchmark Reference

All numeric benchmarks are sourced from *How AI Is Transforming Work at Anthropic* (Dec 2025) — 132 engineers surveyed, 53 interviews, 200,000 Claude Code transcripts analysed.

| Metric | Feb 2025 baseline | Aug 2025 best practice |
|---|---|---|
| Max consecutive tool calls | 9.8 | 21.2 |
| Avg human turns per session | 6.2 | 4.1 |
| Avg task complexity (1–5) | 3.2 | 3.8 |
| New work generated | — | 27% |
| Papercut fix rate | — | 8.6% |

---

## 9. Privacy

The analyzer runs entirely in the browser. Session files never leave your machine except for the summarized inputs sent to the AI provider API:

- **API Call 1** sends: first 2 user messages + last user message per session (capped at 1200 chars), plus turn counts. No full conversation content.
- **API Call 2** sends: up to 20 user messages per session, each capped at 150 characters.
- **API Call 3** sends: aggregated metrics only — no message content.
