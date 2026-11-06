"""Какие статьи корпуса собираются pdflatex без докачки пакетов и без shell-escape (на копиях в work_tex/)."""

import re
import shutil
import subprocess
import time
from pathlib import Path

import run as arxiv

HERE = Path(__file__).resolve().parent
WORK = HERE / "work_tex" / "probe"
TEX = ["pdflatex", "--enable-installer", "-no-shell-escape", "-interaction=nonstopmode"]


def main():
    for paper in sorted(arxiv.CORPUS.iterdir()):
        main_file = arxiv.main_tex(paper)
        if not main_file:
            continue
        d = WORK / paper.name
        if d.exists():
            shutil.rmtree(d)
        shutil.copytree(paper, d)
        m = d / main_file.relative_to(paper)
        start = time.perf_counter()
        for _ in range(2):
            try:
                subprocess.run(TEX + [m.name], cwd=m.parent, capture_output=True, timeout=900)
            except subprocess.TimeoutExpired:
                print(paper.name, "таймаут")
                break
        log = m.with_suffix(".log").read_text(errors="replace") if m.with_suffix(".log").exists() else ""
        missing = re.findall(r"! LaTeX Error: File `([^']+)' not found", log)
        pages = re.search(r"Output written on .*?\((\d+) pages?", log)
        print(f"{paper.name:14} {time.perf_counter() - start:6.1f}c страниц={pages.group(1) if pages else '-'}"
              f" нет файлов: {sorted(set(missing))[:4]}", flush=True)


if __name__ == "__main__":
    main()
