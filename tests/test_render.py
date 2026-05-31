from code_reviewer.main import render_report
from code_reviewer.schemas import Finding, ReviewReport


def _report(findings=None, note="Looks good.", truncated=False):
    return ReviewReport(findings=findings or [], positive_note=note, truncated=truncated)


def _finding(severity="low", dimension="conventions"):
    return Finding(
        dimension=dimension,
        severity=severity,
        file="a.py",
        line_start=1,
        line_end=1,
        issue="some issue",
        suggestion="some fix",
    )


def test_no_findings_message():
    md = render_report(_report())
    assert "No issues found" in md


def test_positive_note_included():
    md = render_report(_report(note="Clean and well-structured."))
    assert "Clean and well-structured" in md


def test_truncation_note_shown():
    md = render_report(_report(truncated=True))
    assert "truncated" in md.lower()


def test_truncation_note_absent_when_false():
    md = render_report(_report(truncated=False))
    assert "truncated" not in md.lower()


def test_severity_ordering():
    findings = [
        _finding(severity="low"),
        _finding(severity="high"),
        _finding(severity="medium"),
    ]
    md = render_report(_report(findings=findings))
    high_pos = md.index("[HIGH]")
    medium_pos = md.index("[MEDIUM]")
    low_pos = md.index("[LOW]")
    assert high_pos < medium_pos < low_pos


def test_file_location_in_output():
    f = Finding(
        dimension="security", severity="high",
        file="src/auth.py", line_start=42, line_end=42,
        issue="hardcoded token", suggestion="use env var",
    )
    md = render_report(_report(findings=[f]))
    assert "src/auth.py" in md
    assert "42" in md


def test_no_line_number_when_absent():
    f = Finding(
        dimension="conventions", severity="low",
        file="utils.py", line_start=None, line_end=None,
        issue="x", suggestion="y",
    )
    md = render_report(_report(findings=[f]))
    assert "utils.py" in md
