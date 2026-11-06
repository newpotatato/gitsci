"""После доработки: gitsci на всех копиях с ошибками (обе выборки) и рисунок, исчезнувший из замечаний."""

import re
from pathlib import Path

import holdout
import run as arxiv

ok = total = 0
miss = []
OPS = {re.sub(r"\W+", "_", k): k for k in arxiv.OPERATORS if k.startswith("J_")}
for work, corpus in ((holdout.WORK, holdout.CORPUS), (arxiv.WORK, arxiv.CORPUS)):
    for paper in sorted(corpus.iterdir()):
        src = arxiv.main_tex(paper)
        if not src or not (work / paper.name).exists():
            continue
        base = arxiv.run_gitsci(paper, src)
        for d in sorted((work / paper.name).iterdir()):
            name = OPS.get(d.name) or ("J_equation_unreferenced (№28)" if d.name.startswith("J_align") else None)
            if not name:
                continue
            new = arxiv.run_gitsci(d, d / src.relative_to(paper)) - base
            total += 1
            hit = any(arxiv.relevant(name, "gitsci", ":".join(k)) for k in new)
            ok += hit
            if not hit:
                miss.append((paper.name, d.name))
print("найдено", ok, "из", total, miss[:8])

for pid in ("1602.04938",):
    p = holdout.CORPUS / pid
    text = " ".join(f.read_text(encoding="utf-8", errors="replace") for f in p.rglob("*.tex"))
    for m in re.finditer(r"\\begin\{figure\*?\}.*?\\end\{figure\*?\}", text, re.S):
        if "fig:inception" in m.group():
            labels = re.findall(r"\\label\{([^}]+)\}", m.group())
            print(labels, [(x, len(re.findall(r"ref\{[^}]*" + re.escape(x) + r"[,}]", text))) for x in labels])
