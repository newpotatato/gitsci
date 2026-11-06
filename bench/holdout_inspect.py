"""Контекст спорных замечаний отложенной выборки для ручной разметки."""

import csv
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
rows = list(csv.DictReader(open(HERE / "holdout_precision.csv", encoding="utf-8-sig")))


def texts(paper):
    return " ".join(re.sub(r"(?<!\\)%.*", "", f.read_text(encoding="utf-8", errors="replace"))
                    for f in (HERE / "corpus_holdout" / paper).rglob("*.tex"))


# заголовки
for p in ("1606.01540", "1707.06347"):
    print(p, "заголовок:", sorted(set(re.findall(r"\\(\w*title\w*)\s*[\[{]", texts(p))))[:6])

# рисунки GCN
t = texts("1609.02907")
for lab in ("fig:karate-club", "fig:model", "fig:semi-emb", "fig:model-depth"):
    print(lab, [" ".join(t[max(0, m.start() - 25):m.end() + 5].split()) for m in re.finditer(re.escape(lab) + r"\b", t)][:5])
for p in ("1602.04938", "1701.07875"):
    for r in rows:
        if r["paper"] == p and r["rule"] == "FMT_FIGURE_UNREFERENCED":
            lab = re.search(r"рисунок (\S+) нет", r["message"]).group(1)
            print(p, lab, len(re.findall(re.escape(lab), texts(p))))
print("subfigure/subfloat в GCN:", len(re.findall(r"\\sub(?:figure|float|caption)", t)))

# формулы
for p in sorted({r["paper"] for r in rows if r["rule"] == "FMT_EQ_UNREFERENCED"}):
    t = texts(p)
    prose = re.sub(r"\\begin\{(equation|align|eqnarray|gather|multline)\*?\}.*?\\end\{\1\*?\}", " ", t, flags=re.S)
    prose = " ".join(prose.split())
    nums = [re.search(r"\(([\w.]+)\)", r["message"]).group(1) for r in rows
            if r["paper"] == p and r["rule"] == "FMT_EQ_UNREFERENCED"]
    wraps = re.findall(r"\\(?:re)?newcommand\*?\{?\\(\w+)\}?(?:\[\d\])?\{[^\n]{0,40}\\(?:eq)?ref\{#1\}", t)
    print(p, "замечаний", len(nums), "номера", nums, "макросы:", wraps[:5])
    for n in nums:
        for m in list(re.finditer(r"(?<![\w^_])\(" + re.escape(n) + r"\)", prose))[:2]:
            print("    голое", n, ":", prose[max(0, m.start() - 50):m.end() + 15])
        for m in list(re.finditer(r"(?:[Ee]q\w*\.?|[Ff]ormula)[~ ]*\(?" + re.escape(n) + r"\b", prose))[:1]:
            print("    словом", n, ":", prose[max(0, m.start() - 30):m.end() + 15])
