"""Выгрузка замечаний gitsci на оригиналах корпуса с контекстом для ручной разметки точности.

Для каждого замечания: фрагмент исходника и подсказки разметчику (есть ли \\nonumber, ищется ли метка
во всех .tex статьи любыми командами, есть ли в статье свои макросы-обёртки над \\ref, ссылки по номеру вида
«Eq. (3)»). Итог: bench/raw/precision_context.md (для чтения) и bench/precision.csv (столбцы для вердикта).

Запуск: python bench/annotate.py
"""

import csv
import re
from pathlib import Path

import run as arxiv
from gitsci.findings import Report
from gitsci.latex import fmt, texdoc

HERE = Path(__file__).resolve().parent


def context(file, line, before=2, after=6):
    lines = Path(file).read_text(errors="replace").split("\n")
    return "\n".join(lines[max(0, line - 1 - before):line - 1 + after])


def main():
    rows, md = [], ["# Замечания gitsci на оригиналах: контекст для разметки", ""]
    for paper in sorted(arxiv.CORPUS.iterdir()):
        main_file = arxiv.main_tex(paper)
        if not main_file:
            continue
        everything = "\n".join(p.read_text(errors="replace") for p in paper.rglob("*.tex"))
        wrappers = re.findall(r"\\(?:re)?newcommand\*?\{?\\(\w+)\}?(?:\[\d\])?\{[^\n]*\\(?:eq)?ref\{#1\}", everything)
        by_number = len(re.findall(r"(?:Eq\.|Equation|eq\.|equation)~?\s*\(\d+\)", everything))
        report = Report()
        fmt.check(texdoc.load(main_file), report, arxiv.PROFILE, arxiv.bib_keys(paper, main_file))
        for f in report.findings:
            if f.severity == "info":
                continue
            file = paper / f.file if not Path(f.file).is_absolute() else Path(f.file)
            if not file.exists():
                file = Path(f.file)
            ctx = context(file, f.line) if f.line else ""
            env = ctx[:600]
            labels = re.findall(r"\\label\{([^}]+)\}", context(file, f.line, 0, 15)) if f.line else []
            label = labels[0] if labels else ""
            uses = len(re.findall(r"\{" + re.escape(label) + r"\}", everything)) - 1 if label else 0
            hints = []
            if f.rule == "FMT_EQ_UNREFERENCED":
                block = re.search(r"\\begin\{equation\}(.*?)\\end\{equation\}", context(file, f.line, 0, 30), re.S)
                body = block.group(1) if block else ""
                if re.search(r"\\(nonumber|notag)", body):
                    hints.append("внутри \\nonumber/\\notag")
                label = (re.findall(r"\\label\{([^}]+)\}", body) or [""])[0]
                uses = len(re.findall(r"\{" + re.escape(label) + r"\}", everything)) - 1 if label else 0
                hints.append(f"метка: {label or 'нет'}, упоминаний метки кроме \\label: {uses}")
                if by_number:
                    hints.append(f"в статье {by_number} ссылок по номеру вида «Eq. (N)»")
            elif f.rule in ("FMT_FIGURE_UNREFERENCED",):
                lab = re.search(r"рисунок (\S+) нет", f.message)
                label = lab.group(1) if lab else label
                uses = len(re.findall(r"\{" + re.escape(label) + r"\}", everything)) - 1
                hints.append(f"метка: {label}, упоминаний кроме \\label: {uses}")
            if wrappers:
                hints.append("свои макросы-ссылки: " + ", ".join(sorted(set(wrappers))))
            rid = f"{paper.name}:{f.rule}:{f.line}:{len(rows)}"
            rows.append({"id": rid, "paper": paper.name, "rule": f.rule, "file": f.file, "line": f.line,
                         "message": f.message, "hints": "; ".join(hints), "verdict": "", "reason": ""})
            md += [f"## {rid}", f"{f.message}  ", f"*{'; '.join(hints)}*", "", "```tex", ctx, "```", ""]
    (HERE / "raw").mkdir(exist_ok=True)
    (HERE / "raw/precision_context.md").write_text("\n".join(md), encoding="utf-8")
    with open(HERE / "precision.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(len(rows), "замечаний")


if __name__ == "__main__":
    main()
