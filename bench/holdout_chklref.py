"""Проверка меток формул, которые chklref считает неиспользуемыми: есть ли на них ссылка в исходнике."""

import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
data = json.loads((HERE / "raw/holdout.json").read_text(encoding="utf-8"))
tot = wrong = 0
for p, info in data["base"].items():
    if info["chklref"] is None:
        continue
    src = " ".join(re.sub(r"(?<!\\)%.*", "", f.read_text(encoding="utf-8", errors="replace"))
                   for f in (HERE / "corpus_holdout" / p).rglob("*.tex"))
    envs = re.findall(r"\\begin\{(equation|align|eqnarray|gather|multline)\}(.*?)\\end\{\1\}", src, re.S)
    eq_labels = {x for _, b in envs for x in re.findall(r"\\label\{([^}]+)\}", b)}
    labels = sorted({k.split("remove label ")[1] for k in info["chklref"] if "remove label" in k})  # chklref печатает метку дважды
    eq = [x for x in labels if x in eq_labels]
    used = [x for x in eq if re.search(r"\\\w*ref\{[^}]*\b" + re.escape(x) + r"\b", src)]
    star = sum("STAR" in k for k in info["chklref"])
    tot += len(eq) + star
    wrong += len(used)
    print(p, "звезда", star, "меток формул", len(eq), "из них со ссылкой", len(used), used[:4],
          "прочих меток", len(labels) - len(eq), [x for x in labels if x not in eq][:6])
print("всего замечаний chklref о формулах", tot, "ложных", wrong)
