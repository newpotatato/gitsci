"""Ручные вердикты по 72 замечаниям gitsci на отложенной выборке и точность аналогов на ней.

Вердикты вынесены после просмотра каждой строки (holdout_inspect.py, holdout_rows.py):
- подрисунки GCN: сам рисунок упомянут, требование выполнено, замечание ложно;
- \\ref{#1} в VGG: это определение макроса, а не ссылка, замечание ложно;
- \\title в Gym и PPO: заголовок набран вручную и есть в статье, требование журнала выполнено, замечание ложно;
- остальные замечания верны: нумерованные формулы без ссылок, рисунки без упоминаний, формулы и \\cite в аннотации.
"""

import csv
import json
import re
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
path = HERE / "holdout_precision.csv"
rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
FALSE = {("1609.02907", "FMT_FIGURE_UNREFERENCED"): "подпись рисунка упомянута, метка стоит на подрисунке",
         ("1602.04938", "FMT_FIGURE_UNREFERENCED"): "другие панели рисунка упомянуты, метка стоит на подрисунке",
         ("1409.1556", "FMT_REF_UNDEFINED"): "\\ref{#1} в определении макроса",
         ("1606.01540", "FMT_TITLE"): "заголовок набран без \\title",
         ("1707.06347", "FMT_TITLE"): "заголовок набран без \\title"}
for r in rows:
    reason = FALSE.get((r["paper"], r["rule"]))
    r["verdict"], r["reason"] = ("неверно", reason) if reason else ("верно", "нарушение подтверждено по исходнику")
with open(path, "w", newline="", encoding="utf-8-sig") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)

total, good = Counter(), Counter()
for r in rows:
    total[r["rule"]] += 1
    good[r["rule"]] += r["verdict"] == "верно"
print({k: f"{good[k]}/{total[k]}" for k in total}, f"всего {sum(good.values())}/{sum(total.values())}")

data = json.loads((HERE / "raw/holdout.json").read_text(encoding="utf-8"))
true_fig = {(r["paper"], re.search(r"рисунок (\S+) нет", r["message"]).group(1)) for r in rows
            if r["rule"] == "FMT_FIGURE_UNREFERENCED" and r["verdict"] == "верно"}
print("верные рисунки gitsci:", sorted(true_fig))
found = [(p, re.search(r"Figure (\S+) is never", k).group(1)) for p, i in data["base"].items() for k in i["textidote_fig"]]
print("TeXtidote рисунков", len(found), "верных по меткам", sum(any(p == a and b.replace("#", "") in c for a, c in true_fig) for p, b in found))
print(sorted(found))
ok = [p for p, i in data["base"].items() if i["chklref"] is not None]
print("chklref отработал:", ok)
print("gitsci формулы на этих статьях:", sum(r["rule"] == "FMT_EQ_UNREFERENCED" and r["paper"] in ok for r in rows))
for p in ok:
    labels = [k.split("remove label ")[1] for k in data["base"][p]["chklref"] if "remove label" in k]
    star = sum("STAR" in k for k in data["base"][p]["chklref"])
    src = " ".join(f.read_text(encoding="utf-8", errors="replace") for f in (HERE / "corpus_holdout" / p).rglob("*.tex"))
    envs = re.findall(r"\\begin\{(equation|align|eqnarray|gather|multline)\}(.*?)\\end\{\1\}", src, re.S)
    eq_labels = {x for _, b in envs for x in re.findall(r"\\label\{([^}]+)\}", b)}
    print(p, "STAR", star, "меток всего", len(labels), "из них формул", sum(x in eq_labels for x in labels),
          "gitsci", sum(r["rule"] == "FMT_EQ_UNREFERENCED" and r["paper"] == p for r in rows))
