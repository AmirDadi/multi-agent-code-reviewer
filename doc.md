# Multi-Agent Code Reviewer — Design & Build Plan (v1)

## 1. Target

An autonomous, **read-only** code reviewer that reviews a single git branch *before* human review. Given a repo, a branch, a base, and a description of the branch's intent, it:

1. detects what changed,
2. **understands how the changed code flows through the repo** (callers, callees, entry points),
3. reviews the change across several dimensions in parallel,
4. consolidates everything into a structured report with severity-ranked findings and one positive note.

It is a **reviewer, not a developer**: it never writes, edits, or executes code.

Design goal: demonstrate **intentional multi-agent decomposition** without a heavy framework. A fast model isolates *what changed*; a tool-using agent builds a *flow model*; specialist models each review *one aspect*; a final reviewer consolidates. Each stage uses the right model for its job.

## 2. Limitations (v1, deliberate scope)

- Reviews **one directory** that is a git repo, scoped to **one branch diff** (`base...branch`), not the whole tree.
- **Read-only.** No file mutation, no test execution, no code generation.
- Diff size is **capped** (max files / max diff KB). On overflow: review top-N most significant files, set `truncated=true`, and say so.
- Comprehension is **bounded**: 1-hop reference tracing, capped files read, low `max_recursion` (see §4.2).
- **No RAG / no code indexing** in v1 (see §6). Flow understanding uses text-search tools at query time, not a precomputed index.
- Single repo, single branch per run. English output only.

## 3. Input

| Input | Description |
|---|---|
| `repo_path` | Path to a local directory containing a git repository. |
| `branch` | Branch to review. |
| `base` | Base branch to diff against (default `main`). Review targets `base...branch`. |
| `description` | Natural-language description of the branch's intent. **Drives Domain Alignment** — without it that agent can't judge whether the code does what it was meant to. |

```python
review(
    repo_path="./my-service",
    branch="feature/owner-intent-scoring",
    base="main",
    description="Add a scoring function that ranks seller leads by intent signal strength.",
)
```

## 4. Agentic Architecture (built on LiteToolLLM)

Built on [LiteToolLLM](https://github.com/AmirDadi/LiteToolLLM) — a thin wrapper over `litellm` giving transparent tool calling + Pydantic-validated structured output, no LangChain/LangGraph. APIs used: `structured_completion`, `astructured_completion`, `response_model=`, `tools=[...]`, `parallel_tool_calls=True`, `max_recursion`.

### 4.1 Pipeline

```
   Input (repo, branch, base, description)
        │
        ▼
┌──────────────────────────────────────────┐
│ Stage 0: Change Detector  (fast LLM)      │
│  tools: git_diff, list_changed_files      │
│  out:   ChangeSet (files, hunks, summary) │
└───────────────────┬──────────────────────┘
                    │ ChangeSet
                    ▼
┌──────────────────────────────────────────┐
│ Stage 0.5: Comprehension Agent (strong)   │   ← understands the flow first
│  tools: read_file, find_references,       │
│         find_definition                   │
│  out:   FlowMap (entry pts, upstream,     │
│         downstream, narrative, confidence)│
└───────────────────┬──────────────────────┘
                    │ ChangeSet + FlowMap + codebase_profile
        ┌───────────┼───────────┐
        ▼           ▼           ▼
  ┌──────────┐┌──────────┐┌──────────┐
  │Conventions││  Domain  ││ Security │      Stage 1: Specialists (parallel)
  │  Agent   ││ Alignment││  Agent   │
  └────┬─────┘└────┬─────┘└────┬─────┘
       │ Finding[] │ Finding[] │ Finding[]
       └───────────┼───────────┘
                   ▼
┌──────────────────────────────────────────┐
│ Stage 2: Final Reviewer  (strongest)      │
│  dedup · drop rejected · rank by severity │
│  · 1 positive note → ReviewReport         │
└───────────────────┬──────────────────────┘
                    ▼
            ReviewReport ──▶ append accept/reject → Memory
```

### 4.2 Stage 0.5 — Comprehension Agent (the flow-understanding step)

A tool-using agent that, before any review happens, builds a model of how the changed code fits the execution flow. This is what lets the reviewer reason about *blast radius* and *intent*, not just local correctness.

**Tools (plain callables):**
- `read_file(path)` — read a changed or related file
- `find_references(symbol)` — who calls this changed function/class (ripgrep under the hood — **no index**)
- `find_definition(symbol)` — what the changed code calls into
- `git_diff()`, `list_changed_files()` — shared

`find_references` via ripgrep is the key move: "who's affected" without a vector/AST index — keeping the no-RAG constraint intact (text search at query time = fine; precomputed index = v2).

**Bounds (so it can't wander):**
- 1-hop reference tracing only (direct callers/callees of changed symbols, not transitive)
- ≤ 15 files read total
- `max_recursion` low (6–8)
- on hitting a cap: stop, emit `confidence="low"`, proceed with what it has

**Output → injected into specialist prompts.** Directly upgrades **Domain Alignment** (sees whether the change is wired into the real flow) and **Security** (spots unvalidated input arriving from upstream callers).

### 4.3 Models per stage (tunable via litellm)

| Stage | Role | Model class | Why |
|---|---|---|---|
| 0 | Change detection | fast (`gemini-flash` / `gpt-4o-mini`) | Mechanical git extraction. |
| 0.5 | Comprehension | strong | Reasoning + tool-loop exploration. |
| 1 | Specialists | mid–strong | Real per-aspect reasoning. |
| 2 | Final reviewer | strongest | Consolidation, judgment, tone. |

### 4.4 Core schemas

```python
class ChangeSet(BaseModel):
    files_changed: list[str]
    summary: str
    truncated: bool

class FlowNode(BaseModel):
    symbol: str
    file: str
    role: Literal["entry_point", "changed", "caller", "callee"]

class FlowMap(BaseModel):
    entry_points: list[str]
    changed_symbols: list[FlowNode]
    upstream: list[FlowNode]      # callers — blast radius
    downstream: list[FlowNode]    # callees — dependencies
    narrative: str                # plain-language "how this flows"
    confidence: Literal["high", "medium", "low"]

class Finding(BaseModel):
    dimension: Literal["conventions", "domain", "security"]
    severity: Literal["high", "medium", "low"]
    file: str
    line_start: int | None
    line_end: int | None
    issue: str
    suggestion: str

class ReviewReport(BaseModel):
    findings: list[Finding]
    positive_note: str
    truncated: bool
```

## 5. Memory

Two **structured** stores — not a vector DB. Memory is *state*, not *retrieval*.

**5a. Codebase profile — `codebase_profile.json`** — learned facts about *this* repo (conventions, domain glossary, observed patterns). Built once, refreshed cheaply, injected into specialist prompts so they review against the repo's *actual* conventions.

```json
{
  "conventions": { "naming": "...", "imports": "...", "error_handling": "..." },
  "domain_glossary": { "Listing": "...", "OwnerIntent": "..." },
  "observed_patterns": ["repository pattern for DB access", "..."]
}
```

**5b. Feedback log — `feedback_log.jsonl`** — append-only accept/reject on past findings. Final reviewer loads it and suppresses previously-rejected findings (dedup by `finding_hash = hash(dimension + file + normalized issue)`). Lightweight RLAIF-style memory, zero ML.

```json
{"finding_hash": "a1b2", "dimension": "conventions", "issue": "...", "verdict": "rejected", "reason": "intentional, per style guide"}
```

**Demo value:** run twice; show the reviewer stopped repeating a rejected suggestion.

Storage: JSON/JSONL in v1; SQLite is a drop-in upgrade. No external service.

## 6. No RAG / Code Indexing in v1

Deliberate. RAG earns its place only when the corpus exceeds the context window and a subset must be retrieved. v1 reviews a single branch diff + changed files + 1-hop neighbors — that fits in context. Flow understanding (§4.2) uses **ripgrep at query time**, not a precomputed index.

**v2 extension point:** for whole-repo / multi-directory review, add embeddings + a lightweight vector store (`sqlite-vec`, or in-memory cosine over NumPy) to retrieve related-but-unchanged files. The seam is clean: the Comprehension Agent already produces a `FlowMap`; retrieval would simply widen the context it can pull.

## 7. Supported Review Dimensions

**v1 — implemented (depth over breadth):**
1. **Conventions** — naming, formatting, imports, structure; judged against the learned `codebase_profile`, not generic rules.
2. **Domain Alignment** — does the change accomplish what `description` says? Missing cases, scope creep, mismatched intent. *The differentiator* — most reviewers lack task context; here it's an input, reinforced by the `FlowMap`.
3. **Security** — injection, hardcoded secrets, unsafe calls, unvalidated input (traced from upstream via the `FlowMap`).

**Stubbed extension points (declared, not built):** Performance · Backward compatibility · Architecture & design. Each is a new specialist plugged into Stage 1 — the pipeline is unchanged, only the agent roster grows.

## 8. Build Plan (target ~60 min)

Ordered so you always have a runnable thing.

**Step 0 — Skeleton (5 min)**
- Project dir, `pip install git+https://github.com/AmirDadi/liteToolLlm.git`, `litellm` keys via env.
- Define all Pydantic schemas (§4.4) in `schemas.py`.

**Step 1 — Tools (10 min)** `tools.py`
- `git_diff`, `list_changed_files` (subprocess on git).
- `read_file` (with the file-size/line cap).
- `find_references`, `find_definition` (ripgrep subprocess).
- Each a plain typed callable with a docstring (LiteToolLLM uses these for tool schemas).

**Step 2 — Stage 0 Change Detector (5 min)** `stages/detect.py`
- `structured_completion(model=FAST, tools=[git_diff, list_changed_files], response_model=ChangeSet, max_recursion=4)`.

**Step 3 — Stage 0.5 Comprehension Agent (10 min)** `stages/comprehend.py`
- `structured_completion(model=STRONG, tools=[read_file, find_references, find_definition], response_model=FlowMap, max_recursion=8)`.
- System prompt enforces the bounds in §4.2.

**Step 4 — Stage 1 Specialists (15 min)** `stages/specialists.py`
- Three system prompts (Conventions, Domain, Security), each seeded with `ChangeSet` + `FlowMap` + `codebase_profile`.
- Run concurrently: `asyncio.gather(*[astructured_completion(..., response_model=list[Finding]) for each])`.

**Step 5 — Memory (5 min)** `memory.py`
- Load/save `codebase_profile.json`; append/read `feedback_log.jsonl`; `finding_hash` + dedup helper.

**Step 6 — Stage 2 Final Reviewer (5 min)** `stages/consolidate.py`
- Take all findings + feedback log → `structured_completion(model=STRONGEST, response_model=ReviewReport)`: dedup, drop rejected, rank, add positive note.

**Step 7 — Orchestrator + CLI (5 min)** `main.py`
- Wire stages; `argparse` for the four inputs; render `ReviewReport` as markdown.

**Step 8 — Demo + writeup (5 min)**
- Run on a small public repo branch. Capture output. Run twice to show feedback memory. Write the 100-word summary.

## 9. Output (Submission Artifact)

- `ReviewReport` rendered as markdown: findings grouped by severity (file/line, issue, fix) + positive note.
- ~100-word summary of idea + approach (challenge requirement).
- Optional: public repo link / screenshots.

## 10. File Layout

```
code_reviewer/
├── main.py            # orchestrator + CLI
├── schemas.py         # Pydantic models
├── tools.py           # git + ripgrep callables
├── memory.py          # profile + feedback log
├── stages/
│   ├── detect.py      # Stage 0
│   ├── comprehend.py  # Stage 0.5
│   ├── specialists.py # Stage 1
│   └── consolidate.py # Stage 2
├── codebase_profile.json
└── feedback_log.jsonl
```

