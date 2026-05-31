import json

import pytest

import code_reviewer.memory as memory
from code_reviewer.schemas import Finding


@pytest.fixture
def finding():
    return Finding(
        dimension="security",
        severity="high",
        file="greeting.py",
        line_start=3,
        line_end=3,
        issue="Hardcoded secret key",
        suggestion="Load from environment variable instead",
    )


# --- finding_hash ---

def test_hash_is_deterministic(finding):
    assert memory.finding_hash(finding) == memory.finding_hash(finding)


def test_hash_differs_by_dimension(finding):
    other = finding.model_copy(update={"dimension": "conventions"})
    assert memory.finding_hash(finding) != memory.finding_hash(other)


def test_hash_differs_by_file(finding):
    other = finding.model_copy(update={"file": "other.py"})
    assert memory.finding_hash(finding) != memory.finding_hash(other)


def test_hash_length(finding):
    assert len(memory.finding_hash(finding)) == 12


# --- codebase profile ---

def test_load_profile_missing(tmp_path):
    assert memory.load_codebase_profile(str(tmp_path)) == {}


def test_load_profile_present(tmp_path):
    (tmp_path / "codebase_profile.json").write_text(
        json.dumps({"conventions": {"naming": "snake_case"}})
    )
    profile = memory.load_codebase_profile(str(tmp_path))
    assert profile["conventions"]["naming"] == "snake_case"


# --- feedback log ---

def test_rejected_hashes_empty_when_no_file(tmp_path):
    assert memory.load_rejected_hashes(str(tmp_path)) == set()


def test_append_rejected_appears_in_hashes(tmp_path, finding):
    memory.append_feedback(finding, verdict="rejected", reason="intentional", base_dir=str(tmp_path))
    rejected = memory.load_rejected_hashes(str(tmp_path))
    assert memory.finding_hash(finding) in rejected


def test_append_accepted_not_in_rejected(tmp_path, finding):
    memory.append_feedback(finding, verdict="accepted", base_dir=str(tmp_path))
    rejected = memory.load_rejected_hashes(str(tmp_path))
    assert memory.finding_hash(finding) not in rejected


def test_feedback_log_is_valid_jsonl(tmp_path, finding):
    memory.append_feedback(finding, verdict="rejected", reason="test", base_dir=str(tmp_path))
    lines = (tmp_path / "feedback_log.jsonl").read_text().strip().splitlines()
    for line in lines:
        entry = json.loads(line)
        assert "finding_hash" in entry
        assert "verdict" in entry
