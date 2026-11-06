"""Эксперимент с внесёнными ошибками: gitsci против chktex и lacheck на корпусе arXiv.

Для каждой статьи и каждого оператора мутации делается копия с одной внесённой ошибкой.
Инструмент «нашёл» ошибку, если на копии у него появилось замечание, которого не было на оригинале
(сравнение мультимножеств (файл, строка, код)). Мутации не меняют число строк, поэтому номера строк сопоставимы.
Шум — число замечаний инструмента на оригинале (это не обязательно ложные срабатывания).

Запуск: python bench/run.py  (нужны chktex и lacheck в PATH, gitsci — из ../gitsci)
"""

import json
import os
import re
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "gitsci"))

from gitsci.findings import Report  # noqa: E402
from gitsci.latex import fmt, texdoc  # noqa: E402

CORPUS, WORK, RAW = HERE / "corpus", HERE / "work", HERE / "raw"

PROFILE = {  # требования из docs/paper/requirements.md, без привязки к журналу
    "abstract": {"required": False, "no_citations": True, "no_math": True},
    "figures": {"require_caption": True, "require_label": True, "require_reference": True},
    "equations": {"number_only_referenced": True},
}


# --- статья -------------------------------------------------------------------

def main_tex(root):
    cands = [p for p in root.rglob("*.tex")
             if re.search(r"\\documentclass", p.read_text(errors="replace"))
             and "\\begin{document}" in p.read_text(errors="replace")]
    return max(cands, key=lambda p: ("abstract" in p.read_text(errors="replace"), p.stat().st_size)) if cands else None


def bib_keys(root, main):
    keys = set()
    for p in list(root.rglob("*.bbl")) + [main]:
        keys |= set(re.findall(r"\\bibitem\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}", p.read_text(errors="replace")))
    for p in root.rglob("*.bib"):
        keys |= set(re.findall(r"@\w+\s*\{\s*([^,\s]+)\s*,", p.read_text(errors="replace")))
    return keys


def doc_files(main):
    doc = texdoc.load(main)
    return doc, list(dict.fromkeys(Path(ln.file) for ln in doc.lines))


# --- операторы мутации ---------------------------------------------------------

SKIP_ENVS = r"figure|table|equation|align|eqnarray|gather|multline|tabular|verbatim|lstlisting|algorithm|thebibliography|tikzpicture|displaymath|math"


def prose_lines(text):
    """Номера строк обычного текста в теле документа (вне формул, таблиц, рисунков)."""
    out, depth, body = [], 0, "\\documentclass" not in text  # файл раздела: весь текст относится к телу статьи
    for i, line in enumerate(text.split("\n")):
        s = line.strip()
        if "\\begin{document}" in s:
            body = True
        depth += len(re.findall(r"\\begin\{(" + SKIP_ENVS + r")\*?\}", s))
        depth -= len(re.findall(r"\\end\{(" + SKIP_ENVS + r")\*?\}", s))
        if (body and depth == 0 and len(s) > 60 and not s.startswith(("\\", "%", "$", "&"))
                and "$" not in s and "%" not in s and "\\\\" not in s and re.search(r"[a-zа-яё]{4,} [a-zа-яё]{4,}", s)):
            out.append(i)
    return out


def _on_prose(fn):
    def op(text, ctx):
        lines = text.split("\n")
        cands = prose_lines(text)
        for i in cands[len(cands) // 2:] + cands[:len(cands) // 2]:
            new = fn(lines[i], ctx)
            if new and new != lines[i]:
                lines[i] = new
                return "\n".join(lines), i + 1
        return None
    return op


def _word(fn):
    def sub(line, ctx):
        m = re.search(r"(?<=\s)([a-zа-яё]{5,})(?=\s)", line)
        return line[:m.start()] + fn(m.group(1)) + line[m.end():] if m else None
    return sub


def _abstract(insert):
    def op(text, ctx):
        m = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", text, re.S)
        if m and m.group(1).strip().startswith("\\input"):
            return None  # текст аннотации в отдельном файле
        if m:
            start, body = m.start(1), m.group(1)
        elif "abstract" in ctx.get("file", "").lower():
            start, body = 0, text
        else:  # шаблон Springer Nature: \abstract{...}
            m = re.search(r"^\\abstract\{", text, re.M)
            if not m:
                return None
            start, body = m.end(), texdoc.read_group(text, m.end() - 1)[0]
        dot = re.search(r"[a-zа-яё]\.\s", body)
        if not dot:
            return None
        pos = start + dot.start() + 1
        return text[:pos] + insert(ctx) + text[pos:], text.count("\n", 0, pos) + 1
    return op


def _blank(s):
    return re.sub(r"[^\n]", "", s)


def op_fig_nocaption(text, ctx):
    for m in re.finditer(r"\\begin\{figure\*?\}.*?\\end\{figure\*?\}", text, re.S):
        c = re.search(r"\\caption\s*(\[[^\]]*\])?\s*\{", m.group())
        if c:
            start = m.start() + c.start()
            arg, end = texdoc.read_group(text, m.start() + c.end() - 1)
            return text[:start] + _blank(text[start:end]) + text[end:], text.count("\n", 0, start) + 1
    return None


def op_fig_unref(text, ctx):
    all_text = ctx["all_text"]
    for m in re.finditer(r"\\begin\{figure\*?\}.*?\\end\{figure\*?\}", text, re.S):
        for lab in re.findall(r"\\label\{([^}]+)\}", m.group()):
            pat = re.compile(r"~?\\(ref|autoref|cref|Cref)\{" + re.escape(lab) + r"\}")
            if pat.search(all_text):
                ctx["also"] = (pat, " 1")  # убрать ссылки во всех файлах статьи
                return text, text.count("\n", 0, m.start()) + 1
    return None


OPERATORS = {
    # требования журналов (номера из docs/paper/requirements.md)
    "J_abstract_cite (№5)": _abstract(lambda c: f"~\\cite{{{c['key']}}}"),
    "J_abstract_math (№6)": _abstract(lambda c: " $x^2$"),
    "J_figure_no_caption (№30)": op_fig_nocaption,
    "J_figure_unreferenced (№31)": op_fig_unref,
    "J_ref_undefined (№38)": _on_prose(lambda ln, c: ln.rstrip() + " See Section~\\ref{sec:missing-xyz} for details."),
    "J_cite_undefined (№38)": _on_prose(lambda ln, c: ln.rstrip() + " This was shown before~\\cite{missing2099}."),
    "J_equation_unreferenced (№28)": _on_prose(lambda ln, c: ln.rstrip() + " Then \\begin{equation} y = x \\end{equation} holds."),
    # типографика и язык (область chktex и lacheck)
    "T_straight_quotes": _on_prose(_word(lambda w: f'"{w}"')),
    "T_ellipsis": _on_prose(lambda ln, c: re.sub(r"([a-zа-яё])\. ", r"\1... ", ln, count=1)),
    "T_no_nbsp_cite": _on_prose(lambda ln, c: re.sub(r"~\\cite", r" \\cite", ln, count=1)),
    "T_space_before_comma": _on_prose(lambda ln, c: re.sub(r"([a-zа-яё]),", r"\1 ,", ln, count=1)),
    "T_double_word": _on_prose(_word(lambda w: f"{w} {w}")),
}


# --- инструменты ----------------------------------------------------------------

def run_chktex(root, main):
    out = subprocess.run(["chktex", "-q", "-f", "%f:%l:%n\n", main.name], cwd=main.parent,
                         capture_output=True, text=True, errors="replace").stdout
    return Counter(tuple(ln.rsplit(":", 2)) for ln in out.splitlines() if ln.count(":") >= 2)


def run_lacheck(root, main):
    out = subprocess.run(["lacheck", main.name], cwd=main.parent, capture_output=True, text=True,
                         errors="replace").stdout
    keys = []
    for ln in out.splitlines():
        m = re.match(r'"(.+?)", line (\d+): (.*)', ln)
        if m:
            keys.append((m.group(1), m.group(2), re.sub(r"\d+", "#", m.group(3))[:60]))
    return Counter(keys)


def run_gitsci(root, main):
    report = Report()
    doc = texdoc.load(main)
    fmt.check(doc, report, PROFILE, bib_keys(root, main))
    return Counter((os.path.relpath(os.path.abspath(f.file), root), str(f.line), f.rule, f.severity)
                   for f in report.findings)


JAR = HERE / "tools" / "textidote.jar"


def _textidote(main, *args):
    out = subprocess.run(["java", "-jar", str(JAR), "--no-color", "--quiet", "--output", "singleline", *args, main.name],
                         cwd=main.parent, capture_output=True, encoding="utf-8", errors="replace").stdout
    keys = []
    for ln in out.splitlines():
        m = re.match(r"(.+?)\(L(\d+)C\d+-\S*\): (.*)", ln)
        if m:
            message = re.sub(r"\d+", "#", m.group(3).split(". Suggestions")[0].rsplit(' "', 1)[0])
            keys.append((m.group(1), m.group(2), message[:80]))
    return Counter(keys)


def run_textidote_sh(root, main):
    """Только структурные правила TeXtidote (sh:*)."""
    return _textidote(main)


def run_textidote_lt(root, main):
    """Структурные правила плюс LanguageTool."""
    return _textidote(main, "--check", texdoc.load(main).language())


TOOLS = {"gitsci": run_gitsci, "chktex": run_chktex, "lacheck": run_lacheck,
         "textidote_sh": run_textidote_sh, "textidote_lt": run_textidote_lt}

# Замечание засчитывается, только если оно про внесённую ошибку (коды chktex: 2 — неразрывный пробел,
# 11 — многоточие, 18 — прямые кавычки, 26 — пробел перед знаком препинания).
RELEVANT = {
    "J_abstract_cite (№5)": {"gitsci": ":FMT_ABSTRACT_CITE:"},
    "J_abstract_math (№6)": {"gitsci": ":FMT_ABSTRACT_MATH:"},
    "J_figure_no_caption (№30)": {"gitsci": ":FMT_FIGURE_CAPTION:"},
    "J_figure_unreferenced (№31)": {"gitsci": ":FMT_FIGURE_UNREFERENCED:"},
    "J_ref_undefined (№38)": {"gitsci": ":FMT_REF_UNDEFINED:", "lacheck": "undefined"},
    "J_cite_undefined (№38)": {"gitsci": ":FMT_CITE_UNDEFINED:", "lacheck": "undefined"},
    "J_equation_unreferenced (№28)": {"gitsci": ":FMT_EQ_UNREFERENCED:"},
    "T_straight_quotes": {"chktex": ":18", "lacheck": "quote"},
    "T_ellipsis": {"chktex": ":11", "lacheck": "ellipsis"},
    "T_no_nbsp_cite": {"chktex": ":2", "lacheck": "~"},
    "T_space_before_comma": {"chktex": ":26", "lacheck": "space"},
    "T_double_word": {"lacheck": "double"},
}


# Формулировки TeXtidote: структурные правила и LanguageTool. Подобраны по документации и выводу до подсчёта итогов.
TEXTIDOTE = {
    "J_figure_no_caption (№30)": "caption",
    "J_figure_unreferenced (№31)": "never referenced",
    "J_ref_undefined (№38)": "undefined",
    "J_cite_undefined (№38)": "undefined",
    "T_straight_quotes": 'instead of ""',
    "T_ellipsis": "ellipsis",
    "T_no_nbsp_cite": "non-breaking",
    "T_space_before_comma": "before the comma",
    "T_double_word": "repe",
}


def relevant(op, tool, key):
    if tool.startswith("textidote"):
        return op in TEXTIDOTE and TEXTIDOTE[op] in key.lower()
    pat = RELEVANT[op].get(tool)
    return bool(pat) and (key.endswith(pat) if pat.startswith(":") and tool == "chktex" else pat in key)


def run_all(root, main):
    cwd = os.getcwd()
    os.chdir(root)  # gitsci пишет пути относительно cwd
    try:
        return {name: fn(root, main) for name, fn in TOOLS.items()}
    finally:
        os.chdir(cwd)


# --- эксперимент ----------------------------------------------------------------

def main():
    RAW.mkdir(exist_ok=True)
    results, noise = [], {}
    for paper in sorted(CORPUS.iterdir()):
        main_file = main_tex(paper)
        if main_file is None:
            print(paper.name, "пропуск: нет исходника LaTeX")
            continue
        doc, files = doc_files(main_file)
        words = len(re.findall(r"[A-Za-z]{2,}", doc.prose))
        keys = sorted(bib_keys(paper, main_file))
        base = run_all(paper, main_file)
        # заметки gitsci уровня info (например, «запись .bib не цитируется») в шум не входят
        noise[paper.name] = {"words": words, **{t: sum(n for k, n in c.items() if k[-1] != "info")
                                                for t, c in base.items()}}
        all_text = "\n".join(f.read_text(errors="replace") for f in files)
        print(paper.name, main_file.relative_to(paper), words, "слов", noise[paper.name], flush=True)

        for op_name, op in OPERATORS.items():
            ctx = {"key": keys[len(keys) // 2] if keys else "smith2000", "all_text": all_text}
            done = None
            for f in [main_file] + [f for f in files if f != main_file]:
                ctx["file"] = f.name
                res = op(f.read_text(errors="replace"), ctx)
                if res:
                    done = (f, *res)
                    break
            if not done:
                results.append({"paper": paper.name, "op": op_name, "applicable": False})
                continue
            target, new_text, line = done
            work = WORK / paper.name / re.sub(r"\W+", "_", op_name)
            if work.exists():
                shutil.rmtree(work)
            shutil.copytree(paper, work)
            wt = work / target.relative_to(paper)
            wt.write_text(new_text, encoding="utf-8", errors="replace")
            if "also" in ctx:
                pat, repl = ctx["also"]
                for f in files:
                    wf = work / f.relative_to(paper)
                    wf.write_text(pat.sub(repl, wf.read_text(errors="replace")), encoding="utf-8")
            mut = run_all(work, work / main_file.relative_to(paper))
            row = {"paper": paper.name, "op": op_name, "applicable": True,
                   "file": str(target.relative_to(paper)), "line": line}
            for t in TOOLS:
                new = [":".join(k) for k in mut[t] - base[t]]
                row[t + "_any"] = bool(new)
                row[t] = any(relevant(op_name, t, k) for k in new)
                row[t + "_new"] = new
            results.append(row)
            print("  ", op_name, {t: row[t] for t in TOOLS}, flush=True)

    (RAW / "results.json").write_text(json.dumps({"noise": noise, "results": results}, ensure_ascii=False, indent=1),
                                      encoding="utf-8")
    summarize(noise, results)


def summarize(noise, results):
    lines = ["# Результаты: внесённые ошибки", "",
             f"Корпус: {len(noise)} статей, мутантов: {sum(r['applicable'] for r in results)}.",
             "В ячейке: найдено по существу / мутантов, в скобках — любое новое замечание, если число другое.", "",
             "| Оператор | Мутантов | " + " | ".join(TOOLS) + " |", "|---|---|" + "---|" * len(TOOLS)]
    for op in OPERATORS:
        rows = [r for r in results if r["op"] == op and r["applicable"]]
        if rows:
            cells = []
            for t in TOOLS:
                hit, any_ = sum(r[t] for r in rows), sum(r[t + "_any"] for r in rows)
                cells.append(f"{hit}/{len(rows)}" + (f" ({any_})" if any_ != hit else ""))
            lines.append(f"| {op} | {len(rows)} | " + " | ".join(cells) + " |")
    for prefix, title in (("J_", "Требования журналов"), ("T_", "Типографика и язык")):
        rows = [r for r in results if r["op"].startswith(prefix) and r["applicable"]]
        if rows:
            cells = [f"**{sum(r[t] for r in rows) / len(rows):.0%}**" for t in TOOLS]
            lines.append(f"| **{title}, полнота** | {len(rows)} | " + " | ".join(cells) + " |")
    lines += ["", "## Шум на оригиналах (замечаний на 1000 слов)", "",
              "| Статья | Слов | " + " | ".join(TOOLS) + " |", "|---|---|" + "---|" * len(TOOLS)]
    for p, n in noise.items():
        lines.append(f"| {p} | {n['words']} | " + " | ".join(f"{1000 * n[t] / max(n['words'], 1):.1f}" for t in TOOLS) + " |")
    total = sum(n["words"] for n in noise.values())
    lines.append("| **Всего** | " + str(total) + " | " +
                 " | ".join(f"**{1000 * sum(n[t] for n in noise.values()) / total:.1f}**" for t in TOOLS) + " |")
    (HERE / "results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


def resummarize():
    """Пересчёт итогов из raw/results.json без повторного прогона (после правки RELEVANT)."""
    data = json.loads((RAW / "results.json").read_text(encoding="utf-8"))
    for r in data["results"]:
        if r["applicable"]:
            for t in TOOLS:
                r[t] = any(relevant(r["op"], t, k) for k in r[t + "_new"])
    (RAW / "results.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    summarize(data["noise"], data["results"])


if __name__ == "__main__":
    resummarize() if "--summary" in sys.argv else main()
