"""
Stage tests use mocked LLM calls — no API keys required.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import code_reviewer.tools as tools
from code_reviewer.memory import finding_hash
from code_reviewer.schemas import (
    ChangeSet,
    Finding,
    FindingList,
    FlowMap,
    FlowNode,
    ReviewReport,
)


@pytest.fixture(autouse=True)
def set_repo(fixture_repo):
    tools.set_repo_root(fixture_repo)


def _resp(content):
    r = MagicMock()
    r.content = content
    return r


def _async_resp(content):
    r = AsyncMock()
    r.content = content
    return r


# --- detect ---

def test_detect_changes_returns_changeset(fixture_repo):
    expected = ChangeSet(files_changed=["greeting.py", "main.py"], summary="Added greeting module", truncated=False)
    with patch("code_reviewer.stages.detect.structured_completion", return_value=_resp(expected)):
        from code_reviewer.stages.detect import detect_changes
        result = detect_changes(fixture_repo, "main", "feature/add-greeting", "test-model")
    assert result.files_changed == ["greeting.py", "main.py"]
    assert result.summary == "Added greeting module"


def test_detect_sets_truncated_flag(fixture_repo, monkeypatch):
    # Simulate more changed files than MAX_FILES
    from code_reviewer.stages import detect as detect_module
    monkeypatch.setattr(detect_module, "MAX_FILES", 1)

    expected = ChangeSet(files_changed=["greeting.py"], summary="stub", truncated=False)
    with patch("code_reviewer.stages.detect.structured_completion", return_value=_resp(expected)):
        from code_reviewer.stages.detect import detect_changes
        result = detect_changes(fixture_repo, "main", "feature/add-greeting", "test-model")
    assert result.truncated is True


# --- consolidate ---

def test_consolidate_returns_report(fixture_repo):
    expected = ReviewReport(findings=[], positive_note="Well done.", truncated=False)
    with patch("code_reviewer.stages.consolidate.structured_completion", return_value=_resp(expected)):
        from code_reviewer.stages.consolidate import consolidate
        result = consolidate(fixture_repo, "test-branch", [], set(), False, "test-model")
    assert result.positive_note == "Well done."


def test_consolidate_pre_filters_rejected(fixture_repo):
    f = Finding(
        dimension="security", severity="high", file="x.py",
        line_start=1, line_end=1, issue="hardcoded secret", suggestion="use env var",
    )
    rejected = {finding_hash(f)}
    expected = ReviewReport(findings=[], positive_note="Clean.", truncated=False)

    captured = {}

    def fake_completion(**kwargs):
        captured["user_msg"] = kwargs["messages"][-1]["content"]
        return _resp(expected)

    with patch("code_reviewer.stages.consolidate.structured_completion", side_effect=fake_completion):
        from code_reviewer.stages.consolidate import consolidate
        result = consolidate(fixture_repo, "test-branch", [f], rejected, False, "test-model")

    # The rejected finding should be filtered before the LLM sees it
    assert "hardcoded secret" not in captured["user_msg"]
    assert result.positive_note == "Clean."


# --- specialists (async) ---

@pytest.mark.asyncio
async def test_run_specialists_aggregates_findings(fixture_repo):
    dummy_findings = FindingList(findings=[
        Finding(dimension="conventions", severity="low", file="a.py",
                line_start=1, line_end=1, issue="x", suggestion="y"),
    ])
    changeset = ChangeSet(files_changed=["a.py"], summary="stub", truncated=False)
    flowmap = FlowMap(
        entry_points=[], changed_symbols=[], upstream=[], downstream=[],
        narrative="stub", confidence="low",
    )

    with patch("code_reviewer.stages.specialists.astructured_completion", return_value=_async_resp(dummy_findings)):
        from code_reviewer.stages.specialists import run_specialists
        findings = await run_specialists(
            repo_path=fixture_repo,
            branch="test-branch",
            description="stub",
            changeset=changeset,
            flowmap=flowmap,
            profile={},
            model="test-model",
        )

    # Three specialists run, each returning 1 finding → 3 total
    assert len(findings) == 3
    assert all(isinstance(f, Finding) for f in findings)
