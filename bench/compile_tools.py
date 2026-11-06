"""Сравнение с инструментами, которым нужна сборка: журнал pdflatex и chklref.

Метод тот же, что в run.py: копия статьи с одной ошибкой, новое замечание сравнивается с оригиналом.
Берутся только статьи, которые собираются без докачки пакетов, и операторы, относящиеся к этим инструментам.
Сборка на копиях в work_tex/, без shell-escape и без установки пакетов. Запуск: python bench/compile_tools.py
"""

import json
import re
import shutil
import subprocess
import time
from collections import Counter
from pathlib import Path

import run as arxiv

HERE = Path(__file__).resolve().parent
WORK = HERE / "work_tex" / "mut"
OPTS = ["--disable-installer", "-no-shell-escape"]
CHKLREF_SECONDS, CHKLREF_BYTES = 180, 64 * 1024 * 1024
# chklref запускает pdflatex через цепочку обёрток, и taskkill /T его не достаёт. Ищем только «свой» pdflatex
# по командной строке, чтобы не задеть другие сборки на компьютере.
KILL_CHKLREF_TEX = ("Get-CimInstance Win32_Process -Filter \"Name='pdflatex.exe'\" | "
                    "Where-Object { $_.CommandLine -like '*RequirePackage{chklref}*' } | "
                    "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }")
OPS = ("J_ref_undefined (№38)", "J_cite_undefined (№38)", "J_equation_unreferenced (№28)", "J_figure_unreferenced (№31)")
FIND = {"J_ref_undefined (№38)": ("latex", "ref:sec:missing-xyz"),
        "J_cite_undefined (№38)": ("latex", "cite:missing2099"),
        "J_equation_unreferenced (№28)": ("chklref", "STAR"),
        "J_figure_unreferenced (№31)": ("chklref", "remove label")}


def run_latex(main):
    log = main.with_suffix(".log")
    for _ in range(2):
        try:
            subprocess.run(["pdflatex", *OPTS, "-interaction=nonstopmode", main.name], cwd=main.parent,
                           capture_output=True, timeout=300)
        except subprocess.TimeoutExpired:
            return None
    text = log.read_text(errors="replace") if log.exists() else ""
    if "Output written" not in text:
        return None
    text = text.replace("\n", "")  # журнал переносит длинные строки
    keys = [f"ref:{m}" for m in re.findall(r"Reference `([^']+)' on page", text)]
    keys += [f"cite:{m}" for m in re.findall(r"Citation `([^']+)' on page", text)]
    return Counter(keys)


def run_chklref(main):
    # в справке chklref написано --tex-options, в коде опция называется --texoptions
    # Сторож: на части статей chklref зацикливается и бесконечно пишет .chk (было 12 ГБ на статье VAE).
    # Тайм-аут subprocess здесь не поможет: он убивает обёртку, а pdflatex остаётся, поэтому гасим всё дерево.
    chk, out_file = main.with_suffix(".chk"), main.parent / "_chklref.out"
    with open(out_file, "w", encoding="utf-8") as fh:
        proc = subprocess.Popen(["chklref", "-q", "--texoptions=" + " ".join(OPTS), main.name], cwd=main.parent,
                                stdout=fh, stderr=subprocess.DEVNULL)
        start = time.monotonic()
        while proc.poll() is None:
            if time.monotonic() - start > CHKLREF_SECONDS or (chk.exists() and chk.stat().st_size > CHKLREF_BYTES):
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
                subprocess.run(["powershell", "-NoProfile", "-Command", KILL_CHKLREF_TEX], capture_output=True)
                proc.wait()
                for _ in range(30):  # файл освобождается не сразу после завершения процесса
                    try:
                        chk.unlink(missing_ok=True)
                        break
                    except PermissionError:
                        time.sleep(1)
                else:
                    raise RuntimeError(f"pdflatex всё ещё держит {chk}")
                return None
            time.sleep(1)
    out = out_file.read_text(encoding="utf-8", errors="replace")
    if "Unused Labels" not in out:  # chklref не справился: None, а не ноль замечаний
        return None
    return Counter(" ".join(ln.split()) for ln in out.splitlines() if ln.startswith("-- "))


def main():
    rows, noise = [], {}
    for paper in sorted(arxiv.CORPUS.iterdir()):
        src = arxiv.main_tex(paper)
        if not src:
            continue
        base_dir = WORK / paper.name / "base"
        if base_dir.exists():
            shutil.rmtree(base_dir)
        shutil.copytree(paper, base_dir)
        base_main = base_dir / src.relative_to(paper)
        base_latex = run_latex(base_main)
        if base_latex is None:
            print(paper.name, "не собирается, исключена", flush=True)
            shutil.rmtree(WORK / paper.name)
            continue
        base = {"latex": base_latex, "chklref": run_chklref(base_main), "gitsci": arxiv.run_gitsci(paper, src)}
        chk_ok = base["chklref"] is not None
        if not chk_ok:
            base["chklref"] = Counter()
        noise[paper.name] = {**{t: sum(c.values()) for t, c in base.items()}, "chklref_ok": chk_ok}
        print(paper.name, noise[paper.name], flush=True)
        _, files = arxiv.doc_files(src)
        all_text = "\n".join(f.read_text(errors="replace") for f in files)
        keys = sorted(arxiv.bib_keys(paper, src))
        for name in OPS:
            ctx = {"key": keys[len(keys) // 2] if keys else "smith2000", "all_text": all_text}
            res = None
            for f in [src] + [f for f in files if f != src]:
                ctx["file"] = f.name
                res = arxiv.OPERATORS[name](f.read_text(errors="replace"), ctx)
                if res:
                    target = f
                    break
            if not res:
                rows.append({"paper": paper.name, "op": name, "applicable": False})
                continue
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
            m = d / src.relative_to(paper)
            latex = run_latex(m) or Counter()
            chk = run_chklref(m) if chk_ok else None
            git = arxiv.run_gitsci(d, m)
            tool, needle = FIND[name]
            new = {"latex": latex - base["latex"], "chklref": (chk or Counter()) - base["chklref"],
                   "gitsci": git - base["gitsci"]}
            row = {"paper": paper.name, "op": name, "applicable": True, "chklref_ok": chk is not None,
                   "latex": any(needle in k for k in new["latex"]) if tool == "latex" else False,
                   "chklref": any(needle in k for k in new["chklref"]) if tool == "chklref" else False,
                   "gitsci": any(arxiv.relevant(name, "gitsci", ":".join(k)) for k in new["gitsci"]),
                   "new": {t: [str(k) for k in c] for t, c in new.items()}}
            rows.append(row)
            print("  ", name, {t: row[t] for t in ("gitsci", "latex", "chklref")}, flush=True)
    arxiv.RAW.mkdir(exist_ok=True)
    (arxiv.RAW / "compile_tools.json").write_text(json.dumps({"noise": noise, "rows": rows}, ensure_ascii=False, indent=1),
                                                 encoding="utf-8")


if __name__ == "__main__":
    main()
