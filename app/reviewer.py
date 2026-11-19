from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ReviewFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    line: int = Field(ge=1)
    severity: Literal["critical", "high", "medium", "low"]
    category: Literal["security", "correctness", "maintainability"]
    title: str
    body: str
    confidence: float = Field(ge=0, le=1)


class ReviewReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    findings: list[ReviewFinding]
    files_reviewed: int = Field(ge=0)
    lines_reviewed: int = Field(ge=0)
    summary: str


class AddedLine(BaseModel):
    path: str
    line: int
    text: str


def added_lines(patch: str) -> Iterator[AddedLine]:
    path: str | None = None
    new_line = 0

    for line in patch.splitlines():
        if line.startswith("+++ b/"):
            path = line[6:]
            continue
        if line.startswith("@@"):
            match = re.search(r"\+(\d+)(?:,\d+)?", line)
            new_line = int(match.group(1)) if match else 0
            continue
        if path is None or line.startswith(("diff ", "index ", "---", "+++")):
            continue
        if line.startswith("+"):
            yield AddedLine(path=path, line=new_line, text=line[1:])
            new_line += 1
        elif line.startswith(" "):
            new_line += 1


_RULES: tuple[tuple[re.Pattern[str], str, str, str, str, float], ...] = (
    (
        re.compile(r"\bexec\s*\("),
        "critical",
        "security",
        "Dynamic code execution",
        "Executing a constructed string can run attacker-controlled code. Avoid `exec`; use an explicit parser or dispatch table.",
        0.96,
    ),
    (
        re.compile(r"\beval\s*\("),
        "high",
        "security",
        "Dynamic expression evaluation",
        "`eval` can execute untrusted input as code. Replace it with a safe parser or validate against an explicit set of values.",
        0.94,
    ),
    (
        re.compile(r"\bsubprocess\.(?:run|Popen|call)\s*\(.*\bshell\s*=\s*True"),
        "high",
        "security",
        "Shell command built through subprocess",
        "Using `shell=True` makes shell metacharacters meaningful. Pass an argument list with `shell=False`, especially when any input is variable.",
        0.91,
    ),
    (
        re.compile(r"\b(?:execute|executemany)\s*\(\s*f[\"'].*(?:SELECT|INSERT|UPDATE|DELETE|WHERE)", re.I),
        "high",
        "security",
        "SQL query interpolates a formatted string",
        "Building a SQL statement with string interpolation can expose query injection. Use parameterized query arguments instead.",
        0.85,
    ),
    (
        re.compile(r"\bpickle\.loads?\s*\("),
        "high",
        "security",
        "Untrusted pickle deserialization",
        "Unpickling untrusted data can execute code. Use a non-executable serialization format or authenticate the data before loading it.",
        0.88,
    ),
    (
        re.compile(r"\byaml\.load\s*\("),
        "medium",
        "security",
        "YAML loaded with a potentially unsafe loader",
        "Use `yaml.safe_load` for untrusted YAML, or pass an explicitly safe loader.",
        0.82,
    ),
    (
        re.compile(r"\bverify\s*=\s*False\b"),
        "medium",
        "security",
        "TLS certificate verification disabled",
        "Disabling certificate verification permits man-in-the-middle attacks. Configure a trusted CA instead.",
        0.87,
    ),
    (
        re.compile(r"\b(?:password|passwd|secret|api_key)\s*=\s*['\"][^'\"]{8,}['\"]", re.I),
        "high",
        "security",
        "Possible hard-coded credential",
        "This assignment resembles a hard-coded credential. Load secrets from a secret manager or environment configuration, and rotate any real credential committed here.",
        0.77,
    ),
)


def review_patch(patch: str) -> ReviewReport:
    findings: list[ReviewFinding] = []
    touched_files: set[str] = set()
    lines_reviewed = 0

    for added in added_lines(patch):
        touched_files.add(added.path)
        lines_reviewed += 1
        code = added.text.split("#", 1)[0]
        for pattern, severity, category, title, body, confidence in _RULES:
            if pattern.search(code):
                findings.append(
                    ReviewFinding(
                        path=added.path,
                        line=added.line,
                        severity=severity,
                        category=category,
                        title=title,
                        body=body,
                        confidence=confidence,
                    )
                )

    if findings:
        summary = f"Found {len(findings)} potential issue(s) across {len(touched_files)} changed file(s)."
    else:
        summary = f"No rule-based findings in {len(touched_files)} changed file(s)."

    return ReviewReport(
        findings=findings,
        files_reviewed=len(touched_files),
        lines_reviewed=lines_reviewed,
        summary=summary,
    )