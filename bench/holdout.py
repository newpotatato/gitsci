"""Проверка на отложенной выборке: 12 статей arXiv, на которых правила gitsci не настраивались.

Правила заморожены до скачивания выборки. Сравнение только там, где есть открытый аналог:
№ 31 и № 28 против chklref, № 31 против TeXtidote, № 38 против журнала pdflatex.
Результат: raw/holdout.json и holdout.md. Запуск: python bench/holdout.py
"""

import json
import re
import shutil
import sys
import time
from pathlib import Path

import fetch
import run as arxiv
from gitsci.findings import Report
from gitsci.latex import fmt, texdoc

import compile_tools as ct

HERE = Path(__file__).resolve().parent
CORPUS, WORK = HERE / "corpus_holdout", HERE / "work_holdout"
PAPERS = {
    "1409.1556": "VGG",
    "1609.02907": "Graph Convolutional Networks",
    "1703.06870": "Mask R-CNN",
    "1411.4028": "QAOA",
    "1602.04938": "LIME",
    "1301.3781": "word2vec",
    "1707.06347": "PPO",
    "1503.02531": "Distilling the Knowledge in a Neural Network",
    "1710.10903": "Graph Attention Networks",
    "1701.07875": "Wasserstein GAN",
    "1312.5602": "Playing Atari with Deep RL",
    "1606.01540": "OpenAI Gym",
}

OPS = {k: arxiv.OPERATORS[k] for k in ("J_ref_undefined (№38)", "J_cite_undefined (№38)", "J_equation_unreferenced (№28)",
                           "J_figure_unreferenced (№31)")}
ALIGN = "J_align_unreferenced (№28)"
OPS[ALIGN] = arxiv._on_prose(lambda ln, c: ln.rstrip() + " Then \\begin{align} y &= x \\\\ z &= w \\end{align} holds.")


def gitsci_lines(paper, main):
    report = Report()
    fmt.check(texdoc.load(main), report, arxiv.PROFILE, arxiv.bib_keys(paper, main))
    return [(f.rule, f.file, f.line, f.message) for f in report.findings if f.severity != "info"]


def mutate(paper, src, files, name, keys, all_text):
    ctx = {"key": keys[len(keys) // 2] if keys else "smith2000", "all_text": all_text}
    res = target = None
    for f in [src] + [f for f in files if f != src]:
        ctx["file"] = f.name
        res = OPS[name](f.read_text(errors="replace"), ctx)
        if res:
            target = f
            break
    if not res:
        return None
    d = WORK / paper.name / re.sub(r"\W+", "_", name)
    if d.exists():
        shutil.rmtree(d)
    shutil.copytree(paper, d)
    (d / target.relative_to(paper)).write_text(res[0], encoding="utf-8", errors="replace")
    if "also" in ctx:
        pat, repl = ctx["also"]
        for f in files:
            wf = d / f.relative_to(paper)
            wf.write_text(pat.sub(repl, wf.read_text(errors="replace")), encoding="utf-8")
    return d / src.relative_to(paper)


def main():
    fetch.ROOT = CORPUS
    for i, pid in enumerate(PAPERS):
        fetch.fetch(pid)
        time.sleep(3)
    rows, base_info = [], {}
    for paper in sorted(CORPUS.iterdir()):
        src = arxiv.main_tex(paper)
        if not src:
            print(paper.name, "нет исходника LaTeX, пропуск", flush=True)
            continue
        b = WORK / paper.name / "base"
        if b.exists():
            shutil.rmtree(b)
        shutil.copytree(paper, b)
        bm = b / src.relative_to(paper)
        ct.OPTS[0] = "--enable-installer"  # первая сборка докачивает пакеты
        latex = ct.run_latex(bm)
        ct.OPTS[0] = "--disable-installer"
        if latex is None:
            print(paper.name, "не собирается, пропуск", flush=True)
            continue
        chk = ct.run_chklref(bm)
        fig = arxiv.run_textidote_sh(paper, src)
        git = arxiv.run_gitsci(paper, src)
        base_info[paper.name] = {"gitsci": gitsci_lines(paper, src), "chklref": sorted(chk) if chk is not None else None,
                                 "textidote_fig": [":".join(k) for k in fig if "never referenced" in k[2]]}
        print(paper.name, src.relative_to(paper), "chklref", "нет отчёта" if chk is None else sum(chk.values()),
              "gitsci", len(base_info[paper.name]["gitsci"]), flush=True)
        _, files = arxiv.doc_files(src)
        all_text = "\n".join(f.read_text(errors="replace") for f in files)
        keys = sorted(arxiv.bib_keys(paper, src))
        for name in OPS:
            m = mutate(paper, src, files, name, keys, all_text)
            if m is None:
                rows.append({"paper": paper.name, "op": name, "applicable": False})
                continue
            new_latex = (ct.run_latex(m) or arxiv.Counter()) - latex
            new_chk = None
            if chk is not None:
                c2 = ct.run_chklref(m)
                new_chk = None if c2 is None else c2 - chk
            new_fig = arxiv.run_textidote_sh(m.parent, m) - fig
            new_git = arxiv.run_gitsci(WORK / paper.name / m.relative_to(WORK / paper.name).parts[0], m) - git
            rows.append({
                "paper": paper.name, "op": name, "applicable": True,
                "gitsci": any(":FMT_" in ":".join(k) and arxiv.relevant(name if name != ALIGN else "J_equation_unreferenced (№28)",
                                                                       "gitsci", ":".join(k)) for k in new_git),
                "latex": any("missing" in k for k in new_latex),
                "chklref": None if new_chk is None else any(("STAR" if "equ" in name or "align" in name else "remove label") in k
                                                            for k in new_chk),
                "textidote": any("never referenced" in k[2] for k in new_fig),
            })
            print("  ", name, {k: rows[-1][k] for k in ("gitsci", "latex", "chklref", "textidote")}, flush=True)
    arxiv.RAW.mkdir(exist_ok=True)
    (arxiv.RAW / "holdout.json").write_text(json.dumps({"base": base_info, "rows": rows}, ensure_ascii=False, indent=1),
                                            encoding="utf-8")
    print("готово", len(base_info), "статей")


if __name__ == "__main__":
    sys.exit(main())
