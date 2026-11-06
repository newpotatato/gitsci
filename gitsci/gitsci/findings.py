"""Результаты проверок и их вывод: текст для человека, JSON и отчёт Code Quality для GitLab MR."""

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

ERROR, WARNING, INFO = "error", "warning", "info"
_ORDER = {ERROR: 0, WARNING: 1, INFO: 2}
# Уровни GitLab Code Quality: https://docs.gitlab.com/ci/testing/code_quality/
_GITLAB_SEVERITY = {ERROR: "major", WARNING: "minor", INFO: "info"}


@dataclass
class Finding:
    rule: str
    severity: str
    message: str
    file: str = ""
    line: int = 0
    hint: str = ""

    def location(self):
        if not self.file:
            return ""
        return f"{self.file}:{self.line}" if self.line else self.file


@dataclass
class Report:
    findings: list = field(default_factory=list)

    def add(self, rule, severity, message, file="", line=0, hint=""):
        self.findings.append(Finding(rule, severity, message, str(file).replace("\\", "/"), line, hint))

    def extend(self, other):
        self.findings.extend(other.findings)

    def count(self, severity):
        return sum(1 for f in self.findings if f.severity == severity)

    def failed(self, fail_on=ERROR):
        limit = _ORDER[fail_on]
        return any(_ORDER[f.severity] <= limit for f in self.findings)

    def sorted(self):
        return sorted(self.findings, key=lambda f: (_ORDER[f.severity], f.file, f.line, f.rule))

    def to_text(self, title=""):
        icons = {ERROR: "✗", WARNING: "!", INFO: "·"}
        lines = [f"== {title}"] if title else []
        for f in self.sorted():
            loc = f.location()
            lines.append(f"{icons[f.severity]} [{f.severity}] {f.rule}: {f.message}" + (f"  ({loc})" if loc else ""))
            if f.hint:
                lines.append(f"    → {f.hint}")
        lines.append(
            f"Итого: ошибок {self.count(ERROR)}, предупреждений {self.count(WARNING)}, заметок {self.count(INFO)}"
        )
        return "\n".join(lines)

    def to_json(self):
        return json.dumps([asdict(f) for f in self.sorted()], ensure_ascii=False, indent=2)

    def to_codequality(self):
        items = []
        for f in self.sorted():
            fingerprint = hashlib.md5(f"{f.rule}|{f.file}|{f.line}|{f.message}".encode()).hexdigest()
            items.append({
                "description": f"{f.rule}: {f.message}" + (f" — {f.hint}" if f.hint else ""),
                "check_name": f.rule,
                "fingerprint": fingerprint,
                "severity": _GITLAB_SEVERITY[f.severity],
                "location": {"path": f.file or ".", "lines": {"begin": max(f.line, 1)}},
            })
        return json.dumps(items, ensure_ascii=False, indent=2)

    def write(self, path, fmt):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_codequality() if fmt == "codequality" else self.to_json(), encoding="utf-8")
