"""Строки формул с замечаниями на отложенной выборке: источник каждой строки для проверки глазами."""

import csv
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
rows = list(csv.DictReader(open(HERE / "holdout_precision.csv", encoding="utf-8-sig")))
for r in rows:
    if r["rule"] != "FMT_EQ_UNREFERENCED":
        continue
    path = HERE / r["file"]
    src = path.read_text(encoding="utf-8", errors="replace").split("\n")
    i = int(r["line"]) - 1
    near = " ".join(" ".join(src[max(0, i - 1):i + 3]).split())
    num = re.search(r"\(([\w.]+)\)", r["message"]).group(1)
    if r["paper"] in ("1301.3781", "1411.4028", "1609.02907", "1503.02531", "1312.5602"):
        print(r["paper"], num, "стр", r["line"], "|", near[:125])
print()
t = (HERE / "corpus_holdout/1301.3781/efficient-v22.tex").read_text(encoding="utf-8", errors="replace")
print([(m.start(), t[m.start() - 60:m.end()].replace("\n", " ")[-75:]) for m in re.finditer(r"\\label\{eq\d\}", t)])
print(re.findall(r"\\ref\{eq\d\}", t), t.count("\\begin{equation}"))
