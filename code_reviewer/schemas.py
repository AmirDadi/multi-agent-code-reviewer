from typing import Literal
from pydantic import BaseModel


class ChangeSet(BaseModel):
    files_changed: list[str]
    summary: str
    truncated: bool = False


class FlowNode(BaseModel):
    symbol: str
    file: str
    role: Literal["entry_point", "changed", "caller", "callee"]


class FlowMap(BaseModel):
    entry_points: list[str]
    changed_symbols: list[FlowNode]
    upstream: list[FlowNode]
    downstream: list[FlowNode]
    narrative: str
    confidence: Literal["high", "medium", "low"]


class Finding(BaseModel):
    dimension: Literal["conventions", "domain", "security"]
    severity: Literal["high", "medium", "low"]
    file: str
    line_start: int | None = None
    line_end: int | None = None
    issue: str
    suggestion: str


class FindingList(BaseModel):
    """Wrapper so litetoolllm can return a list of findings as a typed BaseModel."""
    findings: list[Finding]


class ReviewReport(BaseModel):
    findings: list[Finding]
    positive_note: str
    truncated: bool = False
