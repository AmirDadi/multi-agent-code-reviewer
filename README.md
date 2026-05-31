# multi-agent-code-reviewer

A learning project exploring how to decompose a code review task across multiple LLM agents — each doing one job with the right model for that job.

Given a local git repo, a branch, and a plain-language description of the branch's intent, it reviews the diff and produces a severity-ranked report.

## How it works

The review runs in four stages:

```
Input (repo, branch, base, description)
         │
         ▼
  Stage 0: Change Detector    ← fast model, extracts what changed
         │
         ▼
  Stage 0.5: Comprehension    ← strong model + tools, traces callers/callees
         │
   ┌─────┼─────┐
   ▼     ▼     ▼
 Conv  Domain  Security       ← three specialists in parallel
   └─────┼─────┘
         ▼
  Stage 2: Final Reviewer     ← dedup · rank · positive note → report
```

**Stage 0** uses a fast/cheap model (Gemini Flash) to extract the diff and file list.

**Stage 0.5** uses a stronger model with tool access to trace how the changed code fits into the broader codebase — reading files and grepping for callers/callees (1-hop, no index). This is what lets the later stages reason about blast radius and intent rather than just local syntax.

**Stage 1** runs three specialist reviewers in parallel:
- **Conventions** — naming, imports, formatting, structure
- **Domain alignment** — does the change match what the description says?
- **Security** — secrets, injection, unvalidated input from upstream callers

**Stage 2** deduplicates and ranks findings, suppresses previously-rejected ones, and adds a positive note.

## Design decisions

- **Right model per stage.** Mechanical extraction doesn't need a strong model. Reasoning over tool output does. Parallelism cuts wall-clock time.
- **Flow understanding without RAG.** The comprehension agent uses `ripgrep` at query time. A precomputed index isn't justified for a single branch diff — that's a v2 concern.
- **Feedback memory.** Rejected findings are hashed and suppressed in future runs. Run twice on the same repo to see it stop repeating a rejected suggestion.
- **No framework.** Built on [LiteToolLLM](https://github.com/AmirDadi/LiteToolLLM) — a thin litellm wrapper for structured output + transparent tool calling, no LangChain/LangGraph.
- **Observability.** All LLM calls are traced in Langfuse when credentials are set (zero-code change — litellm callback).

## Installation

```bash
pip install -e ".[dev]"
```

Copy `.env.example` to `.env` and set your API keys.

## Usage

Run against **any other local git repository** — point `--repo` at it:

```bash
python -m code_reviewer.main \
  --repo /path/to/some-other-repo \
  --branch feature/my-branch \
  --base main \
  --description "Add a scoring function that ranks leads by intent signal strength."
```

Options:
- `--out report.md` — write the report to a file instead of stdout
- `--base` — base branch to diff against (default: `main`)

## Running tests

Tests run entirely offline — no API keys needed (LLM calls are mocked).

```bash
pytest
```

## Observability

Set `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` in `.env`. Each stage appears as a named trace in the Langfuse UI. No code changes required.

## Project structure

```
code_reviewer/
├── main.py            # CLI + orchestrator + report renderer
├── schemas.py         # Pydantic models
├── tools.py           # git + ripgrep callables (path-sandboxed)
├── memory.py          # codebase profile loader + feedback log
├── observability.py   # Langfuse via litellm callback
├── config.py          # model selection (overridable via env)
└── stages/
    ├── detect.py      # Stage 0: change detection
    ├── comprehend.py  # Stage 0.5: flow understanding
    ├── specialists.py # Stage 1: parallel reviewers
    └── consolidate.py # Stage 2: final judgment
```

## Extension points

- Add a new specialist in `stages/specialists.py` — the pipeline is unchanged.
- Add a `profile build` command to populate `codebase_profile.json` per-repo.
- Widen comprehension to multi-hop or whole-repo with a lightweight vector store (v2 seam).
