"""Согласие двух разметчиков: доля совпадений и каппа Коэна.

Разметчик 1 — requirements.md (столбец «Авто») и bench/raw/precision_before_fix.csv (вердикты).
и bench/holdout_precision.csv. Разметчик 2 — заполненные листы docs/paper/annotation/*.csv.
"""

import csv
import re
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
DOCS = HERE.parent / "docs/paper"


def kappa(pairs):
    n = len(pairs)
    po = sum(a == b for a, b in pairs) / n
    ca, cb = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / n ** 2
    return po, (po - pe) / (1 - pe) if pe < 1 else 1.0


def read(name):
    return list(csv.DictReader(open(DOCS / "annotation" / name, encoding="utf-8-sig"), delimiter=";"))


def main():
    first = {}
    for line in (DOCS / "requirements.md").read_text(encoding="utf-8").splitlines():
        m = re.match(r"\| (\d+) \| .+? \| .+? \| (?:О|RU|INT) \| (А|Ч|Н) \|", line)
        if m:
            first[m.group(1)] = m.group(2)
    col = "Автоматизируемо (А — полностью, Ч — частично, Н — нет)"
    latin = str.maketrans("AHC", "АНЧ")  # латинские буквы, похожие на кириллицу
    second = {r["№"]: r[col].strip().upper().translate(latin) for r in read("requirements_sheet.csv") if r[col].strip()}
    filled = bool(second)
    if second:
        po, k = kappa([(first[n], v) for n, v in second.items()])
        print(f"Требования: размечено {len(second)}, совпадение {po:.0%}, каппа Коэна {k:.2f}")
        print("  расхождения в №:", ", ".join(n for n, v in second.items() if first[n] != v) or "нет")

    mine = {r["id"]: r["verdict"] for r in csv.DictReader(open(HERE / "raw/precision_before_fix.csv",
                                                                encoding="utf-8-sig"))}
    norm = {"да": "верно", "нет": "неверно"}
    pairs = [(mine[r["id"]], norm.get(r["Верно? (да/нет)"].strip().lower(), "?"))
             for r in read("precision_spotcheck.csv") if r["Верно? (да/нет)"].strip()]
    if pairs:
        po, k = kappa(pairs)
        print(f"Точность (выборка): размечено {len(pairs)}, совпадение {po:.0%}, каппа Коэна {k:.2f}")

    held = {f"{r['paper']}:{r['rule']}:{r['line']}": r["verdict"]
            for r in csv.DictReader(open(HERE / "holdout_precision.csv", encoding="utf-8-sig"))}
    held_pairs = [(held[r["id"]], norm.get(r["Верно? (да/нет)"].strip().lower(), "?"))
                  for r in read("precision_spotcheck_holdout.csv") if r["Верно? (да/нет)"].strip()]
    if held_pairs:
        po, k = kappa(held_pairs)
        print(f"Точность (отложенная): размечено {len(held_pairs)}, совпадение {po:.0%}, каппа Коэна {k:.2f}")
    if not (filled or pairs or held_pairs):
        print("Листы ещё не заполнены")


if __name__ == "__main__":
    main()
