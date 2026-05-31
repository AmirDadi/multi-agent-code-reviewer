import hashlib
import json
from pathlib import Path

from code_reviewer.schemas import Finding

PROFILE_FILE = "codebase_profile.json"
FEEDBACK_FILE = "feedback_log.jsonl"


def finding_hash(finding: Finding) -> str:
    raw = f"{finding.dimension}:{finding.file}:{finding.issue[:80]}"
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def load_codebase_profile(base_dir: str = ".") -> dict:
    path = Path(base_dir) / PROFILE_FILE
    if path.exists():
        return json.loads(path.read_text())
    return {}


def load_rejected_hashes(base_dir: str = ".") -> set[str]:
    path = Path(base_dir) / FEEDBACK_FILE
    if not path.exists():
        return set()
    rejected = set()
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        if entry.get("verdict") == "rejected":
            rejected.add(entry["finding_hash"])
    return rejected


def append_feedback(
    finding: Finding,
    verdict: str,
    reason: str = "",
    base_dir: str = ".",
) -> None:
    path = Path(base_dir) / FEEDBACK_FILE
    entry = {
        "finding_hash": finding_hash(finding),
        "dimension": finding.dimension,
        "file": finding.file,
        "issue": finding.issue,
        "verdict": verdict,
        "reason": reason,
    }
    with path.open("a") as f:
        f.write(json.dumps(entry) + "\n")
