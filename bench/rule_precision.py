"""Точность аналогов на оригиналах по тем же требованиям, что у gitsci.

№ 31 (рисунок без ссылки): TeXtidote sh:figref против FMT_FIGURE_UNREFERENCED. Замечание верно,
если метка не встречается ни в одной команде-ссылке во всех .tex статьи (\\ref, \\autoref, \\cref, своих макросах).
№ 28 (формула с номером без ссылки): chklref против FMT_EQ_UNREFERENCED на собираемых статьях. Замечание ложно,
если на формулу ссылаются номером, вписанным вручную (eqnumbers.py).
"""

import csv
import json
import re
import subprocess
from pathlib import Path

import eqnumbers
import run as arxiv
from gitsci.latex import texdoc

HERE = Path(__file__).resolve().parent
NOISE = json.loads((HERE / "raw/compile_tools.json").read_text(encoding="utf-8"))["noise"]
OK_PAPERS = [p for p, n in NOISE.items() if n["chklref_ok"]]  # статьи, где chklref выдал отчёт


def strip_comments(text):
    return re.sub(r"(?<!\\)%.*", "", text)


def figures():
    total = wrong = 0
    details = []
    for paper in sorted(arxiv.CORPUS.iterdir()):
        m = arxiv.main_tex(paper)
        if not m:
            continue
        everything = "\n".join(strip_comments(p.read_text(errors="replace")) for p in paper.rglob("*.tex"))
        out = subprocess.run(["java", "-jar", str(arxiv.JAR), "--no-color", "--quiet", "--output", "singleline", m.name],
                             cwd=m.parent, capture_output=True, encoding="utf-8", errors="replace").stdout
        for label in sorted(set(re.findall(r"Figure (\S+) is never referenced", out))):
            total += 1
            # упоминание метки где угодно, кроме \label{...}
            pattern = re.escape(label)
            used = re.search(r"(?<!\\label)\{[^{}]*\b" + pattern + r"\b[^{}]*\}", everything)
            wrong += bool(used)
            details.append((paper.name, label, "ложно" if used else "верно"))
    return total, wrong, details


def equations():
    data = {}
    for paper in OK_PAPERS:
        src = arxiv.main_tex(arxiv.CORPUS / paper)
        doc = texdoc.load(src)
        hand = {doc.locate(o)[1] for o, n in eqnumbers.numbered(doc) if eqnumbers.referenced_by_number(doc, n)}
        base = HERE / "work_tex/mut" / paper / "base"
        from compile_tools import run_chklref
        found = [k for k in run_chklref(base / src.relative_to(arxiv.CORPUS / paper)) if "STAR" in k]
        lines = [int(re.search(r"line\s+(\d+)", k).group(1)) for k in found]
        rows = [r for r in csv.DictReader(open(HERE / "raw/precision_before_fix.csv", encoding="utf-8-sig"))
                if r["paper"] == paper and r["rule"] == "FMT_EQ_UNREFERENCED"]
        data[paper] = {"chklref": len(lines), "wrong": sum(ln in hand for ln in lines), "gitsci_before": len(rows),
                       "gitsci_before_wrong": sum(r["verdict"] != "верно" for r in rows)}
    return data


def main():
    total, wrong, details = figures()
    eq = equations()
    rows = list(csv.DictReader(open(HERE / "raw/precision_before_fix.csv", encoding="utf-8-sig")))
    gitsci_fig = [r for r in rows if r["rule"] == "FMT_FIGURE_UNREFERENCED"]
    out = {"textidote_figref": {"total": total, "wrong": wrong, "details": details},
           "gitsci_figure": {"total": len(gitsci_fig), "wrong": sum(r["verdict"] != "верно" for r in gitsci_fig)},
           "chklref_equations": eq}
    (HERE / "raw/rule_precision.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: {x: y for x, y in v.items() if x != "details"} for k, v in out.items()}, ensure_ascii=False))
    print([d for d in details if d[2] == "ложно"])


if __name__ == "__main__":
    main()
