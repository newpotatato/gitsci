"""Сценарии ошибок между артефактами, в процессе и на уровне документа (на синтетическом проекте статьи).

Собирается «чистый» проект: статья, .bib, реестр, план, запуски экспериментов, рисунок с метаданными.
В каждую копию вносится одна ошибка. Засчитывается, если у gitsci появилось ожидаемое правило, которого
не было на чистом проекте. chktex и lacheck прогоняются на тех же копиях для сравнения.
Метки апрува читаются из заглушки GitLab (стенд для эксперимента не нужен).

Запуск: python bench/scenarios.py
"""

import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections import Counter
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "gitsci"))

from gitsci import experiments, figures, plan, registry  # noqa: E402
from gitsci.findings import Report  # noqa: E402
from gitsci.latex import fmt, style, texdoc  # noqa: E402
from gitsci.profile import load as load_profile  # noqa: E402

import run as arxiv  # noqa: E402  (chktex, lacheck, корпус)

WORK = HERE / "work" / "scenarios"
TODAY = date(2026, 10, 30)
PROFILE = load_profile("lab")
PROFILE["figures"] = {**PROFILE["figures"], "require_run_id": True}
BS = "\\"


# --- чистый проект ---------------------------------------------------------------

def bib_entries(n=16, old=0, own=0):
    out = []
    for i in range(n):
        year = 2005 + i % 5 if i < old else 2022 + i % 5
        author = "Петрова, Мария" if i < own else f"Author{chr(65 + i % 26)}, Alan and Coauthor{i}, Bob"
        out.append(f"@article{{ref{i:02d},\n  author = {{{author}}},\n  title = {{Study number {i} of noisy "
                   f"optimization}},\n  journal = {{Journal of Tests}},\n  year = {{{year}}}\n}}\n")
    return "\n".join(out)


def paper_tex(n_refs=16):
    cites = ", ".join(f"{BS}cite{{ref{i:02d}}}" for i in range(n_refs))
    return rf"""\documentclass{{article}}
\usepackage{{amsmath}}
\usepackage{{graphicx}}
\usepackage{{hyperref}}
\newcommand{{\keywords}}[1]{{\par\noindent Keywords: #1}}
\newcommand{{\affil}}[1]{{}}
\newcommand{{\email}}[1]{{}}
\title{{Adaptive SPSA with momentum for noisy optimization}}
\author{{Elena Smirnova \and Maria Petrova}}
\affil{{Stochastic Optimization Lab, Example University}}
\email{{e.smirnova@lab.example.org}}
\begin{{document}}
\maketitle
\begin{{abstract}}
We study stochastic approximation with simultaneous perturbation and momentum under measurement noise. Momentum reduces the final error at an equal budget of measurements.
\end{{abstract}}
\keywords{{stochastic approximation, momentum, noisy optimization}}

\input{{sections/intro}}

\section{{Methods}}
The update rule is given in Equation~\eqref{{eq:update}} and uses a fixed step size.
\begin{{equation}}
x_{{k+1}} = x_k - a_k g_k \label{{eq:update}}
\end{{equation}}

\section{{Results}}
Figure~\ref{{fig:conv}} shows the convergence of both methods over the iterations.
\begin{{figure}}
\centering
\includegraphics[width=0.8\linewidth]{{../../figures/conv.pdf}}
\caption{{Convergence of the methods.}}
\label{{fig:conv}}
\end{{figure}}

\section{{Discussion}}
The effect of momentum grows with the noise level in our experiments.

\section{{Conclusion}}
Momentum is a simple way to make the method more robust.

\section*{{Data availability}}
Code and data are available in the project repository.

\section*{{Funding}}
Not applicable.

\section*{{Competing interests}}
The authors declare no competing interests.

\section*{{Author contributions}}
All authors contributed equally.

\section*{{Use of generative AI}}
Generative AI was not used to write this text.

\bibliographystyle{{unsrt}}
\bibliography{{../references}}
\end{{document}}
""".replace("\\input{sections/intro}", "\\input{sections/intro}\n\nPrior work is reviewed in " + cites + ".")


INTRO_EN = "\\section{Introduction}\nStochastic approximation is a classic tool for optimization with noisy measurements of the objective.\n"
INTRO_RU = "\\section{Введение}\nСтохастическая аппроксимация давно используется для оптимизации функций с шумом измерений.\n"


def plan_yml(intro_status="done", approved_by="smirnova"):
    return f"""paper: Adaptive SPSA
supervisor: smirnova
sections:
  - id: intro
    owner: petrova
    ru: paper/ru/sections/intro.tex
    en: paper/en/sections/intro.tex
    due_ru: 2026-10-01
    due_en: 2026-10-20
    status: {intro_status}
    approved_by: {approved_by}
    approved_mr: 1
  - id: methods
    owner: petrova
    ru: paper/ru/sections/methods.tex
    en: paper/en/sections/methods.tex
    due_ru: 2026-11-20
    due_en: 2026-12-01
    status: planned
"""


RUN_ID = "20261015-120000-momentum"


def build(d):
    if d.exists():
        shutil.rmtree(d)
    (d / "paper/en/sections").mkdir(parents=True)
    (d / "paper/ru/sections").mkdir(parents=True)
    (d / "paper/en/main.tex").write_text(paper_tex(), encoding="utf-8")
    (d / "paper/en/main.log").write_text("Output written on main.pdf (12 pages, 345678 bytes).\n")
    (d / "paper/en/sections/intro.tex").write_text(INTRO_EN, encoding="utf-8")
    (d / "paper/ru/sections/intro.tex").write_text(INTRO_RU, encoding="utf-8")
    (d / "paper/references.bib").write_text(bib_entries(), encoding="utf-8")
    (d / "plan.yml").write_text(plan_yml(), encoding="utf-8")
    reg = d / "registry"
    (reg / "people").mkdir(parents=True)
    shutil.copytree(ROOT / "templates/lab-registry/cv", reg / "cv")
    for pid in ("smirnova-ev", "petrova-ma"):
        shutil.copy(ROOT / f"templates/lab-registry/people/{pid}.yml", reg / "people")
    run = d / "experiments/runs" / RUN_ID
    run.mkdir(parents=True)
    (run / "meta.json").write_text(json.dumps({"run_id": RUN_ID, "exit_code": 0, "metrics": {"err": 0.01},
                                               "git": {"commit": "abc123", "dirty": False}}), encoding="utf-8")
    (d / "figures").mkdir()
    (d / "figures/conv.pdf").write_bytes(b"%PDF-1.4\n%%EOF\n")
    (d / "figures/conv.meta.json").write_text(json.dumps({
        "fonts": [{"text": "iteration", "size": 8}], "series_colors": ["#0072B2", "#E69F00"],
        "width_in": 6.0, "height_in": 3.5, "run_id": RUN_ID}), encoding="utf-8")


# --- сценарии ---------------------------------------------------------------------

def edit(path, old, new):
    text = path.read_text(encoding="utf-8")
    assert old in text, (path, old)
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def yml_set(path, key, value):
    text = path.read_text(encoding="utf-8")
    path.write_text(re.sub(rf"^{key}:.*$", f"{key}: {value}", text, count=1, flags=re.M), encoding="utf-8")


def tex(d):
    return d / "paper/en/main.tex"


def fig_meta(d, **kw):
    p = d / "figures/conv.meta.json"
    meta = json.loads(p.read_text(encoding="utf-8"))
    meta.update(kw)
    p.write_text(json.dumps({k: v for k, v in meta.items() if v is not None}), encoding="utf-8")


SCENARIOS = {
    # между артефактами: статья ↔ реестр
    "X_author_misspelled": ("AUTH_NAME_SPELLING", lambda d: edit(tex(d), "Maria Petrova", "Mariya Petrova")),
    "X_author_not_in_registry": ("AUTH_NOT_IN_REGISTRY", lambda d: edit(tex(d), r"\and Maria", r"\and John Doe \and Maria")),
    "X_email_not_in_registry": ("AUTH_EMAIL", lambda d: edit(tex(d), "e.smirnova@lab", "smirnova.personal@lab")),
    "X_affiliation_mismatch": ("AUTH_AFFILIATION", lambda d: edit(
        tex(d), r"\affil{Stochastic Optimization Lab, Example University}", r"\affil{Other Institute}")),
    "X_registry_stale": ("AUTH_REGISTRY_STALE", lambda d: yml_set(d / "registry/people/petrova-ma.yml", "updated", "2025-12-01")),
    "X_orcid_typo": ("REG_ORCID_CHECKSUM", lambda d: yml_set(d / "registry/people/petrova-ma.yml", "orcid", "0000-0003-1958-4206")),
    # между артефактами: литература ↔ реестр (русское написание своей фамилии)
    "X_self_citation": ("BIB_SELF_CITATION", lambda d: (d / "paper/references.bib").write_text(bib_entries(own=5), encoding="utf-8")),
    # между артефактами: рисунок ↔ эксперимент
    "X_figure_orphan_run": ("EXP_FIGURE_ORPHAN", lambda d: fig_meta(d, run_id="20261001-000000-lost")),
    "X_figure_without_run": ("FIG_NO_RUN", lambda d: fig_meta(d, run_id=None)),
    "X_run_dirty_no_patch": ("EXP_PATCH_MISSING", lambda d: edit(d / f"experiments/runs/{RUN_ID}/meta.json",
                                                                 '"dirty": false', '"dirty": true')),
    "X_figure_cvd": ("FIG_CVD", lambda d: fig_meta(d, series_colors=["#d62728", "#2ca02c"])),
    # процесс: план и апрув
    # раздел methods в статусе planned, а английский текст уже написан
    "P_en_before_approval": ("PLAN_EN_BEFORE_APPROVAL", lambda d: (d / "paper/en/sections/methods.tex").write_text(
        "\\section{Methods}\nThe update rule uses a fixed step size and a momentum term.\n", encoding="utf-8")),
    "P_approval_forged": ("PLAN_APPROVAL_FORGED", None),  # метку ставит студент: см. MockGitLab
    "P_approval_by_student": ("PLAN_APPROVAL", lambda d: edit(d / "plan.yml", "approved_by: smirnova", "approved_by: petrova")),
    # документ: требования из набора для статьи
    "D_no_ai_declaration": ("FMT_DECLARATION_MISSING", lambda d: edit(tex(d), r"\section*{Use of generative AI}", "")),
    "D_keywords_semicolons": ("FMT_KEYWORDS_FORMAT", lambda d: edit(tex(d), "approximation, momentum,", "approximation; momentum;")),
    "D_too_many_pages": ("FMT_PAGES", lambda d: (tex(d).with_suffix(".log")).write_text("Output written on main.pdf (27 pages, 1 bytes).\n")),
    "D_sorted_bibliography": ("FMT_CITE_ORDER", lambda d: edit(tex(d), r"\bibliographystyle{unsrt}", r"\bibliographystyle{plain}")),
    "D_too_few_refs": ("BIB_TOO_FEW", lambda d: [edit(tex(d), f", \\cite{{ref{i:02d}}}", "") for i in range(8, 16)]),
    "D_old_refs": ("BIB_NOT_RECENT", lambda d: (d / "paper/references.bib").write_text(bib_entries(old=12), encoding="utf-8")),
    "D_section_missing": ("FMT_SECTION_MISSING", lambda d: edit(tex(d), r"\section{Discussion}", "")),
    "D_long_abstract": ("FMT_ABSTRACT_LENGTH", lambda d: edit(tex(d), "budget of measurements.", "budget of measurements." + " More words here." * 90)),
    "D_long_title": ("FMT_TITLE", lambda d: edit(tex(d), "for noisy optimization}", "for noisy optimization" + " and more" * 8 + "}")),
    "D_forbidden_package": ("FMT_PACKAGE_FORBIDDEN", lambda d: edit(tex(d), r"\usepackage{hyperref}", "\\usepackage{hyperref}\n\\usepackage{subfigure}")),
}


class MockGitLab:
    """Заглушка API: события меток MR !1. forged=True — метку ru-approved поставил студент."""
    enabled = True

    def __init__(self, forged=False):
        self.user = "petrova" if forged else "smirnova"

    def pid(self, project):
        return 1

    def get_all(self, path):
        return [{"action": "add", "label": {"name": "ru-approved"}, "user": {"username": self.user}}]


# --- прогон ----------------------------------------------------------------------

def run_gitsci(d, forged=False):
    report = Report()
    cwd = os.getcwd()
    os.chdir(d)
    try:
        main = Path("paper/en/main.tex")
        doc = texdoc.load(main)
        from gitsci import bib
        entries = bib.parse("paper/references.bib")
        people = registry.check("registry", report, today=TODAY)
        fmt.check(doc, report, PROFILE, {e["key"] for e in entries})
        fmt.check_references(doc, report, PROFILE, entries, people, today=TODAY)
        style.check(doc, report, PROFILE["style"])
        registry.check_paper_authors(doc, people, report, today=TODAY)
        figures.check("figures", report, PROFILE["figures"])
        experiments.check(report, "figures")
        plan.check("plan.yml", report, today=TODAY, gitlab=MockGitLab(forged), project="lab/paper")
    finally:
        os.chdir(cwd)
    return report


def keys(report):
    return Counter((f.rule, f.file, f.line) for f in report.findings if f.severity != "info")


def linters(d):
    main = d / "paper/en/main.tex"
    return {"chktex": arxiv.run_chktex(d, main), "lacheck": arxiv.run_lacheck(d, main),
            "textidote_sh": arxiv.run_textidote_sh(d, main), "textidote_lt": arxiv.run_textidote_lt(d, main)}


def main():
    base_dir = WORK / "base"
    build(base_dir)
    base = run_gitsci(base_dir)
    base_keys = keys(base)
    base_lint = linters(base_dir)
    print("Чистый проект, замечаний gitsci (без info):", sum(base_keys.values()))
    for f in base.findings:
        if f.severity != "info":
            print("   ", f.rule, f.message)

    rows = []
    for name, (rule, mutate) in SCENARIOS.items():
        d = WORK / name
        build(d)
        if mutate:
            mutate(d)
        rep = run_gitsci(d, forged=name == "P_approval_forged")
        new = keys(rep) - base_keys
        lint = linters(d)
        row = {"scenario": name, "rule": rule, "gitsci": any(k[0] == rule for k in new),
               "gitsci_new": sorted({k[0] for k in new}),
               # у линтеров нет правил для этих требований: любое новое замечание — побочное (сдвиг строк и т. п.)
               **{t: False for t in lint}, **{t + "_any": bool(lint[t] - base_lint[t]) for t in lint}}
        rows.append(row)
        print(f"{name:28} {rule:26} gitsci={row['gitsci']}  {row['gitsci_new']}")

    timing = measure_time(base_dir)
    (HERE / "raw").mkdir(exist_ok=True)
    (HERE / "raw/scenarios.json").write_text(json.dumps({"rows": rows, "timing": timing}, ensure_ascii=False,
                                                        indent=1), encoding="utf-8")
    write_md(rows, timing, sum(base_keys.values()))


def measure_time(base_dir, repeat=3):
    """Секунды на статью: gitsci (формат) и chktex на корпусе arXiv, полный набор gitsci на проекте."""
    out = {}
    if not arxiv.CORPUS.exists():  # корпус не скачан (python bench/fetch.py): замер пропускаем
        return out
    for paper in sorted(arxiv.CORPUS.iterdir()):
        m = arxiv.main_tex(paper)
        if not m:
            continue
        t = {}
        for tool, fn in arxiv.TOOLS.items():
            start = time.perf_counter()
            for _ in range(repeat):
                cwd = os.getcwd()
                os.chdir(paper)
                try:
                    fn(paper, m)
                finally:
                    os.chdir(cwd)
            t[tool] = (time.perf_counter() - start) / repeat
        out[paper.name] = t
    start = time.perf_counter()
    for _ in range(repeat):
        run_gitsci(base_dir)
    out["project_full"] = {"gitsci": (time.perf_counter() - start) / repeat}
    return out


LINTERS = ("chktex", "lacheck", "textidote_sh", "textidote_lt")
GROUPS = {"X": "Между артефактами", "P": "Процесс (план и апрув)", "D": "Документ (набор для статьи)"}


def write_md(rows, timing, base_n):
    lines = ["# Результаты: сценарии на проекте статьи", "",
             f"Чистый проект: {base_n} замечаний gitsci (без info). Сценариев: {len(rows)}.", "",
             "| Сценарий | Ожидаемое правило | gitsci | " + " | ".join(LINTERS) + " |", "|---|---|---|" + "---|" * len(LINTERS)]
    mark = {True: "да", False: "нет"}
    for r in rows:
        lint = [mark[r[t]] + (" (побочное замечание)" if r[t + "_any"] else "") for t in LINTERS]
        lines.append(f"| {r['scenario']} | {r['rule']} | {mark[r['gitsci']]} | " + " | ".join(lint) + " |")
    lines += ["", "| Группа | Сценариев | gitsci | " + " | ".join(LINTERS) + " |", "|---|---|---|" + "---|" * len(LINTERS)]
    for g, title in GROUPS.items():
        rs = [r for r in rows if r["scenario"].startswith(g + "_")]
        lines.append(f"| {title} | {len(rs)} | " + " | ".join(
            f"{sum(r[t] for r in rs)}/{len(rs)}" for t in ("gitsci", *LINTERS)) + " |")
    lines += ["", "## Время, секунды на статью (среднее из 3 прогонов)", "",
              "| Статья | gitsci | " + " | ".join(LINTERS) + " |", "|---|---|" + "---|" * len(LINTERS)]
    for p, t in timing.items():
        lines.append(f"| {p} | " + " | ".join(f"{t[k]:.2f}" if k in t else "" for k in ("gitsci", *LINTERS)) + " |")
    (HERE / "scenarios.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
