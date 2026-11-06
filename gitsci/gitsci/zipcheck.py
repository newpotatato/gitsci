"""Проверка архива «по нашей форме»: студент присылает один zip — получает ответ «принят / не принят».

1. Безопасная распаковка: размер, число файлов, zip-бомбы, пути с «..» и абсолютные пути.
2. Структура по форме (gitsci/data/zipform.yml): обязательные файлы и папки, запрещённый мусор.
3. Все проверки проекта (latex, bib, figures, plan, experiments) на распакованном содержимом.
Вердикт: принят, если нет ни одной ошибки (error).
"""

import fnmatch
import html
import os
import tempfile
import zipfile
from importlib import resources
from pathlib import Path, PurePosixPath

import yaml

from . import bib, experiments, figures, plan, profile, registry
from .findings import ERROR, WARNING, Report
from .latex import fmt, style, texdoc


def load_form(path=None):
    if path:
        return yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return yaml.safe_load(resources.files("gitsci.data").joinpath("zipform.yml").read_text(encoding="utf-8"))


def _root_prefix(names):
    """Если всё лежит в одной папке (как при «Сжать папку»), её имя считается корнем."""
    tops = {n.split("/", 1)[0] for n in names if n.strip("/")}
    if len(tops) == 1:
        top = tops.pop()
        if any(n.startswith(top + "/") for n in names):
            return top + "/"
    return ""


def inspect(zip_path, form, report):
    """Структура архива без распаковки. Возвращает (zipfile, prefix) или (None, '')."""
    name = Path(zip_path).name
    size_mb = Path(zip_path).stat().st_size / 2**20
    if size_mb > form.get("max_size_mb", 50):
        report.add("ZIP_TOO_BIG", ERROR, f"Архив {size_mb:.1f} МБ больше {form['max_size_mb']} МБ", name,
                   hint="Уберите данные и бинарники: в архиве только код, текст и рисунки")
        return None, ""
    try:
        zf = zipfile.ZipFile(zip_path)
        bad = zf.testzip()
    except zipfile.BadZipFile:
        report.add("ZIP_BAD", ERROR, "Это не zip-архив или он повреждён", name)
        return None, ""
    if bad:
        report.add("ZIP_BAD", ERROR, f"Повреждён файл внутри архива: {bad}", name)
        return None, ""

    infos = [i for i in zf.infolist()]
    names = [i.filename.replace("\\", "/") for i in infos]
    if len(infos) > form.get("max_files", 3000):
        report.add("ZIP_TOO_MANY_FILES", ERROR, f"В архиве {len(infos)} файлов", name)
        return None, ""
    unpacked = sum(i.file_size for i in infos) / 2**20
    if unpacked > form.get("max_unpacked_mb", 200):
        report.add("ZIP_TOO_BIG", ERROR, f"После распаковки {unpacked:.0f} МБ (> {form['max_unpacked_mb']})", name)
        return None, ""
    for n in names:
        p = PurePosixPath(n)
        if p.is_absolute() or ".." in p.parts or ":" in p.parts[0]:
            report.add("ZIP_UNSAFE_PATH", ERROR, f"Опасный путь в архиве: {n}", name)
            return None, ""

    prefix = _root_prefix(names)
    rel = [n[len(prefix):] for n in names if n.startswith(prefix)]
    present = set(rel) | {str(PurePosixPath(r).parent) + "/" for r in rel} | {
        "/".join(PurePosixPath(r).parts[:i]) + "/" for r in rel for i in range(1, len(PurePosixPath(r).parts))}

    for req in form.get("required", []):
        if "path" in req:
            if req["path"] not in present:
                report.add("ZIP_MISSING", ERROR, req.get("message", f"Нет {req['path']}"), name,
                           hint="Структура — как в шаблоне lab/paper-template")
        elif not any(p in present for p in req.get("any", [])):
            report.add("ZIP_MISSING", ERROR, req.get("message", "Нет ни одного из: " + ", ".join(req["any"])), name)
    if "main.tex" in present and not any(r.startswith("paper/") for r in rel):
        report.add("ZIP_FLAT_OVERLEAF", ERROR, "Похоже на выгрузку Overleaf: main.tex лежит в корне", name,
                   hint="Положите статью в paper/ru/ или paper/en/, код в src/, рисунки в figures/")
    for rule in form.get("forbidden", []):
        hits = [r for r in rel if fnmatch.fnmatch(r, rule["glob"]) or fnmatch.fnmatch(PurePosixPath(r).name, rule["glob"])]
        if hits:
            report.add("ZIP_FORBIDDEN_FILE", WARNING, rule.get("message", f"Лишние файлы {rule['glob']}") +
                       f": {len(hits)} шт. (например, {hits[0]})", name, hint="Удалите их из архива")
    return zf, prefix


def extract(zf, prefix, dest):
    for info in zf.infolist():
        n = info.filename.replace("\\", "/")
        if not n.startswith(prefix) or n.endswith("/"):
            continue
        target = Path(dest) / n[len(prefix):]
        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(info) as src, open(target, "wb") as dst:
            dst.write(src.read())


def check(zip_path, form=None, offline=False, registry_root=None, workdir=None):
    """Возвращает (report, accepted, extracted_dir)."""
    form = form or load_form()
    report = Report()
    zf, prefix = inspect(zip_path, form, report)
    if zf is None:
        return report, False, None
    dest = Path(workdir or tempfile.mkdtemp(prefix="gitsci-zip-"))
    extract(zf, prefix, dest)

    cfg_path = dest / "gitsci.yml"
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}
    prof = profile.load(cfg.get("profile", "lab"))
    papers = [p for p in cfg.get("papers", ["paper/en/main.tex", "paper/ru/main.tex"]) if (dest / p).exists()]
    if not papers:  # архив не по форме — всё равно покажем, что не так с текстом
        papers = [str(p.relative_to(dest)).replace("\\", "/") for p in sorted(dest.rglob("*.tex"))
                  if "\\documentclass" in p.read_text(encoding="utf-8", errors="replace")]
    bib_path = dest / cfg.get("bib", "paper/references.bib")
    people = registry.load(registry_root) if registry_root and Path(registry_root).exists() else None

    cwd = os.getcwd()
    os.chdir(dest)  # относительные пути в отчёте — как внутри архива
    try:
        checks = form.get("checks", [])
        bib_keys = {e["key"] for e in bib.parse(bib_path)} if bib_path.exists() else None
        if "latex" in checks:
            for paper in papers:
                doc = texdoc.load(paper)
                fmt.check(doc, report, prof, bib_keys)
                style.check(doc, report, prof.get("style", {}))
                if people is not None:
                    registry.check_paper_authors(doc, people, report)
        if "bib" in checks and bib_path.exists():
            bib.check(bib_path.relative_to(dest), report, prof.get("references", {}), offline=offline,
                      crossref=bib.Crossref(offline=offline, cache_path=Path(cwd, bib.CACHE).resolve()))
        if "figures" in checks:
            figures.check(cfg.get("figures", "figures"), report, prof.get("figures", {}))
        if "plan" in checks and Path("plan.yml").exists():
            plan.check("plan.yml", report)
        if "experiments" in checks:
            experiments.check(report, cfg.get("figures", "figures"))
    finally:
        os.chdir(cwd)
    accepted = not report.failed("error")
    return report, accepted, dest


def verdict_text(report, accepted, name):
    head = f"Архив {name}: {'ПРИНЯТ ✓' if accepted else 'НЕ ПРИНЯТ ✗'}"
    return head + "\n" + report.to_text()


def verdict_html(report, accepted, name):
    color = "#1a7f37" if accepted else "#cf222e"
    rows = "".join(
        f"<tr class='{f.severity}'><td>{f.severity}</td><td><code>{html.escape(f.rule)}</code></td>"
        f"<td>{html.escape(f.message)}{'<br><small>→ ' + html.escape(f.hint) + '</small>' if f.hint else ''}</td>"
        f"<td><code>{html.escape(f.location())}</code></td></tr>" for f in report.sorted())
    return (f"<h2 style='color:{color}'>{'Принят' if accepted else 'Не принят'}: {html.escape(name)}</h2>"
            f"<p>Ошибок {report.count('error')}, предупреждений {report.count('warning')}, "
            f"заметок {report.count('info')}.</p>"
            f"<table><thead><tr><th>Уровень</th><th>Правило</th><th>Что не так</th><th>Где</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>")
