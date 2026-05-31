# Changelog

All notable changes to this project are documented here.

## [0.1.0] - 2026-05-31

### Added

- 4-stage multi-agent review pipeline
  - Stage 0: change detection via fast LLM (Gemini Flash)
  - Stage 0.5: comprehension agent with `read_file`, `find_references`, `find_definition` tools
  - Stage 1: parallel specialist reviewers — conventions, domain alignment, security
  - Stage 2: final consolidation with severity ranking and dedup
- `FindingList` wrapper model so litetoolllm can return typed finding lists
- Feedback memory: append-only JSONL log with `finding_hash` dedup; rejected findings suppressed in future runs
- Optional `codebase_profile.json` injection into specialist prompts
- Langfuse observability via litellm `success_callback`/`failure_callback` — enabled automatically when credentials are present
- Path sandbox: `read_file` and `_safe_path` reject traversal outside repo root
- Symbol variant resolution for grep: camelCase, snake_case, and PascalCase matched in one regex
- CLI: `--repo`, `--branch`, `--base`, `--description`, `--out`
- Markdown report renderer with severity ordering and truncation notice
- Model selection via env vars (`REVIEWER_FAST_MODEL`, `REVIEWER_STRONG_MODEL`, etc.)
- Unit tests for tools, memory, schemas, render — all offline, no API keys
- Mocked stage tests including async specialist runner
- Fixture git repo in `conftest.py` with a feature branch containing a hardcoded secret
