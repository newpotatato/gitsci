"""Вердикты разметки точности для bench/precision.csv (критерии в docs/paper/benchmark.md).

Критерий: замечание верно, если в исходнике действительно нарушено требование из requirements.md
в его журнальной формулировке. Для FMT_EQ_UNREFERENCED ссылкой считается и \\ref/\\eqref, и номер, вписанный
вручную («(1.2)», «Eq. 3»): требование журнала про ссылку в тексте, а не про команду LaTeX.
"""

import csv
from pathlib import Path

import eqnumbers
import run as arxiv
from gitsci.latex import texdoc

HERE = Path(__file__).resolve().parent

REASON = {
    "FMT_ABSTRACT_MATH": "в аннотации формула в $...$",
    "FMT_ABSTRACT_CITE": "в аннотации \\cite",
    "FMT_FIGURE_UNREFERENCED": "метка рисунка нигде не упоминается, своих макросов-ссылок в статье нет",
    "FMT_FIGURE_LABEL": "в окружении figure есть \\caption, но нет \\label",
    "FMT_EQ_UNREFERENCED": "нумерованная формула, ссылок ни командой, ни номером вручную нет",
}


def hand_referenced():
    out = {}
    for paper in sorted(arxiv.CORPUS.iterdir()):
        m = arxiv.main_tex(paper)
        if m:
            doc = texdoc.load(m)
            out[paper.name] = {doc.locate(o)[1] for o, n in eqnumbers.numbered(doc) if eqnumbers.referenced_by_number(doc, n)}
    return out


def main():
    path = HERE / "precision.csv"
    rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
    hand = hand_referenced()
    for r in rows:
        if r["rule"] == "FMT_EQ_UNREFERENCED" and int(r["line"]) in hand.get(r["paper"], set()):
            r["verdict"], r["reason"] = "неверно", "на формулу ссылаются номером, вписанным вручную"
        else:
            r["verdict"], r["reason"] = "верно", REASON[r["rule"]]
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    ok = sum(r["verdict"] == "верно" for r in rows)
    print(f"верно {ok} из {len(rows)} ({ok / len(rows):.0%})")
    for rule in sorted({r["rule"] for r in rows}):
        rs = [r for r in rows if r["rule"] == rule]
        print(f"  {rule}: {sum(r['verdict'] == 'верно' for r in rs)}/{len(rs)}")


if __name__ == "__main__":
    main()
