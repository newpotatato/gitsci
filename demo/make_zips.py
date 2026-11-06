"""Демо-архивы для страницы сдачи: python demo/make_zips.py → demo/zips/*.zip

horoshiy.zip         — проект paper-neuro по форме, с черновиком RU-введения (принимается)
plohoy-overleaf.zip  — плоская выгрузка Overleaf с типичными ошибками (не принимается)
"""

import shutil
import tempfile
import zipfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
TEMPLATE = ROOT.parent / "templates" / "paper-project"
OUT = ROOT / "zips"

INTRO_RU = r"""\section{Введение}\label{sec:intro}
Спайковые нейронные сети обучают методами, которым не нужен градиент функции потерь.
Метод SPSA оценивает градиент по двум измерениям потерь независимо от числа весов \cite{spall1992}.
В работе SPSA применяется к обучению сети из 200 нейронов на задаче классификации.
"""

OVERLEAF_MAIN = r"""\documentclass{article}
\usepackage{graphicx}
\begin{document}
\title{SPSA for spiking networks}
\maketitle
It is worth noting that SPSA plays a crucial role; we use it here.
\begin{equation}
L
=
\sum_i
\ell_i
\end{equation}
\includegraphics{fig1.png}
\bibliography{refs}
\end{document}
"""


def zip_dir(src, dst, root):
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(Path(src).rglob("*")):
            if f.is_file() and "__pycache__" not in f.parts:
                z.write(f, f"{root}/{f.relative_to(src).as_posix()}")


def main():
    OUT.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        proj = Path(tmp) / "paper-neuro"
        shutil.copytree(TEMPLATE, proj, ignore=shutil.ignore_patterns("__pycache__", ".claude"))
        plan = yaml.safe_load((proj / "plan.yml").read_text(encoding="utf-8"))
        plan["paper"] = "SPSA-обучение спайковых нейросетей"
        plan["milestone"]["title"] = "Статья: SPSA-обучение спайковых нейросетей"
        for s in plan["sections"]:
            s["owner"] = "petrova"
        plan["sections"][0]["status"] = "draft_ru"
        (proj / "plan.yml").write_text(yaml.safe_dump(plan, allow_unicode=True, sort_keys=False), encoding="utf-8")
        (proj / "paper" / "ru" / "sections" / "intro.tex").write_text(INTRO_RU, encoding="utf-8")
        zip_dir(proj, OUT / "horoshiy.zip", "paper-neuro")

    with zipfile.ZipFile(OUT / "plohoy-overleaf.zip", "w") as z:
        z.writestr("main.tex", OVERLEAF_MAIN)
        z.writestr("refs.bib", "@article{x, title={Something}, doi={10.1000/fake}}\n")
        z.writestr("main.aux", "")
        z.writestr("__MACOSX/._main.tex", "")
    print("ok:", *sorted(p.name for p in OUT.iterdir()))


if __name__ == "__main__":
    main()
