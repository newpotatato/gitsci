"""Готовит демо-проект paper-spsa из шаблона: заголовок, аннотация, ключевые слова.

Запуск: python demo/prepare_demo.py  (идемпотентно)
"""

import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEMPLATE = ROOT.parent / "templates" / "paper-project"
DEMO = ROOT / "paper-spsa"
MR3 = ROOT / "overlays" / "mr3-results"

META = {
    "en": ("Adaptive SPSA with momentum for noisy black-box optimization",
           "We study simultaneous perturbation stochastic approximation (SPSA) with momentum for optimization "
           "under measurement noise. On a ten-dimensional noisy quadratic function, momentum $\\beta = 0.6$ "
           "reduces the final squared error compared to classical SPSA at an equal measurement budget.",
           "stochastic approximation, SPSA, momentum, noisy optimization"),
    "ru": ("Адаптивный SPSA с моментом для оптимизации зашумлённых функций",
           "Исследуется стохастическая аппроксимация с одновременным возмущением (SPSA) с моментом при шуме "
           "измерений. На зашумлённой квадратичной функции размерности 10 момент $\\beta = 0.6$ уменьшает "
           "итоговую квадратичную ошибку по сравнению с классическим SPSA при равном числе измерений.",
           "стохастическая аппроксимация, SPSA, момент, оптимизация с шумом"),
}
PETROVA = {"en": "Mariya Petrova", "ru": "Мария Петрова"}  # EN — с опечаткой: в реестре «Maria»


def fill(text, lang):
    title, abstract, kw = META[lang]
    text = re.sub(r"\\title\{[^}]*\}", lambda m: "\\title{" + title + "}", text, count=1)
    text = re.sub(r"(\\begin\{abstract\}\n).*?(\n\\end\{abstract\})", lambda m: m.group(1) + abstract + m.group(2),
                  text, count=1, flags=re.S)
    return re.sub(r"\\keywords\{[^}]*\}", lambda m: "\\keywords{" + kw + "}", text, count=1)


def main():
    for lang in ("en", "ru"):
        src = (TEMPLATE / "paper" / lang / "main.tex").read_text(encoding="utf-8")
        demo = fill(src, lang)
        (DEMO / "paper" / lang / "main.tex").write_text(demo, encoding="utf-8")
        smirnova = "\\author[1]{Elena Smirnova}" if lang == "en" else "\\author[1]{Елена Смирнова}"
        assert smirnova in demo
        mr3 = demo.replace(smirnova, "\\author[1]{" + PETROVA[lang] + "}\n" + smirnova)
        (MR3 / "paper" / lang / "main.tex").write_text(mr3, encoding="utf-8")
    shutil.copy(TEMPLATE / "AGENTS.md", DEMO / "AGENTS.md")
    print("ok")


if __name__ == "__main__":
    main()
