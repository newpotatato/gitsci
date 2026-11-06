"""Отложенная выборка после доработки: замечания gitsci, сверка формул с chklref. Сравнение уже не «слепое»."""

import json
import re
from collections import Counter
from pathlib import Path

import holdout
import run as arxiv

data = json.loads((arxiv.RAW / "holdout.json").read_text(encoding="utf-8"))
total = Counter()
for paper in sorted(holdout.CORPUS.iterdir()):
    src = arxiv.main_tex(paper)
    if not src:
        continue
    found = holdout.gitsci_lines(paper, src)
    total.update(f[0] for f in found)
    info = data["base"].get(paper.name)
    if info and info["chklref"] is not None:
        text = " ".join(re.sub(r"(?<!\\)%.*", "", f.read_text(encoding="utf-8", errors="replace")) for f in paper.rglob("*.tex"))
        envs = re.findall(r"\\begin\{(equation|align|eqnarray|gather|multline)\}(.*?)\\end\{\1\}", text, re.S)
        eq_labels = {x for _, b in envs for x in re.findall(r"\\label\{([^}]+)\}", b)}
        labels = sorted({k.split("remove label ")[1] for k in info["chklref"] if "remove label" in k})  # chklref печатает метку дважды
        un = [x for x in labels if x in eq_labels and not re.search(r"\\\w*ref\{[^}]*\b" + re.escape(x) + r"\b", text)]
        star = sum("STAR" in k for k in info["chklref"])
        print(paper.name, "gitsci формул", sum(f[0] == "FMT_EQ_UNREFERENCED" for f in found), "chklref без ложных", star + len(un))
print(dict(total), sum(total.values()))
