"""Листы для независимой разметки вторым экспертом (без вердиктов первого разметчика).

1. docs/paper/annotation/requirements_sheet.csv — 46 требований, столбец «Автоматизируемо» пустой.
2. docs/paper/annotation/precision_spotcheck.csv — 15 случайных замечаний gitsci (до доработки правила формул)
   с фрагментом исходника, столбец «Верно?» пустой.
3. docs/paper/annotation/precision_spotcheck_holdout.csv — то же для отложенной выборки.
"""

import csv
import random
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
DOCS = HERE.parent / "docs/paper"
OUT = DOCS / "annotation"


def requirements():
    rows = []
    for line in (DOCS / "requirements.md").read_text(encoding="utf-8").splitlines():
        m = re.match(r"\| (\d+) \| (.+?) \| (.+?) \| (О|RU|INT) \|", line)
        if m:
            rows.append({"№": m.group(1), "Требование": m.group(2), "Источники": m.group(3),
                         "Автоматизируемо (А — полностью, Ч — частично, Н — нет)": "", "Комментарий": ""})
    return rows


def spotcheck(n=15, seed=2026):
    rows = list(csv.DictReader(open(HERE / "raw/precision_before_fix.csv", encoding="utf-8-sig")))
    random.Random(seed).shuffle(rows)
    out = []
    for r in rows[:n]:
        lines = (HERE / r["file"]).read_text(errors="replace").split("\n")
        line = int(r["line"])
        frag = "\n".join(lines[max(0, line - 2):line + 6])
        out.append({"id": r["id"], "Статья (arXiv)": r["paper"], "Файл:строка": f"{r['file']}:{line}",
                    "Замечание gitsci": r["message"], "Фрагмент исходника": frag,
                    "Верно? (да/нет)": "", "Комментарий": ""})
    return out


def spotcheck_holdout(n=15, seed=2026):
    rows = list(csv.DictReader(open(HERE / "holdout_precision.csv", encoding="utf-8-sig")))
    random.Random(seed).shuffle(rows)
    out = []
    for r in rows[:n]:
        lines = (HERE / r["file"]).read_text(errors="replace").split("\n")
        line = int(r["line"])
        frag = "\n".join(lines[max(0, line - 2):line + 6])
        out.append({"id": f"{r['paper']}:{r['rule']}:{line}", "Статья (arXiv)": r["paper"],
                    "Файл:строка": f"{r['file']}:{line}", "Замечание gitsci": r["message"],
                    "Фрагмент исходника": frag, "Верно? (да/нет)": "", "Комментарий": ""})
    return out


def write(name, rows):
    with open(OUT / name, "w", newline="", encoding="utf-8-sig") as fh:  # BOM: Excel откроет кириллицу
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), delimiter=";")
        w.writeheader()
        w.writerows(rows)
    print(OUT / name, len(rows))


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for name, make in [("requirements_sheet.csv", requirements), ("precision_spotcheck.csv", spotcheck),
                       ("precision_spotcheck_holdout.csv", spotcheck_holdout)]:
        if not (OUT / name).exists():  # заполненный лист не затираем
            write(name, make())
