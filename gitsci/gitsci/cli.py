"""CLI: gitsci <команда>. Конфигурация проекта — gitsci.yml в корне репозитория."""

import argparse
import os
import sys
from pathlib import Path

import yaml

from . import bib, dashboard, experiments, figures, plan, profile, publish, registry, zipcheck
from .findings import Report
from .gitlab_api import GitLab
from .latex import fmt, style, texdoc

DEFAULT_CONFIG = {
    "profile": "lab",
    "papers": ["paper/en/main.tex"],
    "bib": "paper/references.bib",
    "figures": "figures",
    "plan": "plan.yml",
    "registry": None,
}


def load_config(path="gitsci.yml"):
    cfg = dict(DEFAULT_CONFIG)
    if Path(path).exists():
        cfg.update(yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {})
    if os.environ.get("GITSCI_REGISTRY"):
        cfg["registry"] = os.environ["GITSCI_REGISTRY"]
    return cfg


def _finish(report, args, title):
    if sys.stdout.encoding.lower() != "utf-8" and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(report.to_text(title))
    if getattr(args, "json", None):
        report.write(args.json, "json")
    if getattr(args, "codequality", None):
        report.write(args.codequality, "codequality")
    return 1 if report.failed(args.fail_on) else 0


# --- команды -------------------------------------------------------------------

def cmd_latex(args, cfg):
    prof = profile.load(args.profile or cfg["profile"])
    report = Report()
    bib_keys, entries = None, None
    bib_path = Path(cfg["bib"]) if cfg.get("bib") else None
    if bib_path and bib_path.exists():
        entries = bib.parse(bib_path)
        bib_keys = {e["key"] for e in entries}
    people = registry.load(cfg["registry"]) if cfg.get("registry") and Path(cfg["registry"]).exists() else None
    for paper in args.papers or cfg["papers"]:
        if not Path(paper).exists():
            report.add("FMT_NO_PAPER", "error", f"Файл статьи не найден: {paper}", paper)
            continue
        doc = texdoc.load(paper)
        fmt.check(doc, report, prof, bib_keys)
        if entries is not None:
            fmt.check_references(doc, report, prof, entries, people)
        style.check(doc, report, prof.get("style", {}))
        if prof.get("authors", {}).get("check"):
            if people is None:
                report.add("AUTH_NO_REGISTRY", "info", "Реестр участников не подключён — авторы не сверены", paper,
                           hint="Укажите registry в gitsci.yml или GITSCI_REGISTRY")
            else:
                registry.check_paper_authors(doc, people, report)
    return _finish(report, args, f"LaTeX ({prof.get('name')})")


def cmd_style(args, cfg):
    prof = profile.load(args.profile or cfg["profile"])
    report = Report()
    for paper in args.papers:
        style.check(texdoc.load(paper), report, prof.get("style", {}))
    return _finish(report, args, "Стиль текста")


def cmd_bib(args, cfg):
    prof = profile.load(args.profile or cfg["profile"])
    report = Report()
    path = args.file or cfg["bib"]
    if not Path(path).exists():
        report.add("BIB_NO_FILE", "error", f"Нет файла {path}", path)
    else:
        bib.check(path, report, prof.get("references", {}), offline=args.offline)
    return _finish(report, args, "Библиография")


def cmd_figures(args, cfg):
    prof = profile.load(args.profile or cfg["profile"])
    report = Report()
    figures.check(args.dir or cfg["figures"], report, prof.get("figures", {}))
    return _finish(report, args, "Графики")


def cmd_plan(args, cfg):
    report = Report()
    path = args.file or cfg["plan"]
    if args.sync:
        gl = GitLab()
        project = args.project or os.environ.get("CI_PROJECT_PATH")
        if not gl.enabled or not project:
            raise SystemExit("Нужны GITSCI_API_TOKEN (или GITLAB_TOKEN) и --project / CI_PROJECT_PATH")
        for url in plan.sync_issues(path, gl, project):
            print(url)
        return 0
    if not Path(path).exists():
        report.add("PLAN_MISSING", "error", "Нет plan.yml: статья пишется по плану из разделов", path)
    else:
        gl = GitLab()
        plan.check(path, report, gitlab=gl if gl.enabled else None,
                   project=args.project or os.environ.get("CI_PROJECT_PATH"))
    return _finish(report, args, "План статьи")


def cmd_registry(args, cfg):
    report = Report()
    root = args.root or cfg.get("registry") or "."
    people = registry.check(root, report)
    if args.table:
        out = Path(args.table)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.with_suffix(".md").write_text(registry.table_markdown(people), encoding="utf-8")
        out.with_suffix(".html").write_text(registry.table_html(people), encoding="utf-8")
        print(f"Таблица: {out.with_suffix('.md')}, {out.with_suffix('.html')}")
    if args.remind:
        gl = GitLab()
        project = args.project or os.environ.get("CI_PROJECT_PATH")
        if not gl.enabled or not project:
            raise SystemExit("Для --remind нужны GITSCI_API_TOKEN и --project / CI_PROJECT_PATH")
        for url in registry.remind(people, gl, project):
            print("Напоминание:", url)
    return _finish(report, args, "Реестр участников")


def cmd_exp(args, cfg):
    if args.action == "run":
        cmd = args.command
        if not cmd:
            raise SystemExit("Укажите команду после --, например: gitsci exp run -n test -- python train.py")
        run_id, code = experiments.run(args.name, cmd, args.output or [], args.note or "")
        print(f"\nЗапуск сохранён: experiments/runs/{run_id} (код {code})")
        return code
    if args.action == "list":
        print(experiments.show_list())
        return 0
    if args.action == "diff":
        print(experiments.diff(args.a, args.b))
        return 0
    report = Report()
    experiments.check(report, cfg.get("figures"))
    return _finish(report, args, "Эксперименты")


def cmd_all(args, cfg):
    """Все проверки разом — то же, что делает CI."""
    codes = []
    for fn, extra in ((cmd_latex, {"papers": None}), (cmd_bib, {"file": None}), (cmd_figures, {"dir": None}),
                      (cmd_plan, {"file": None, "sync": False, "project": None}),
                      (cmd_exp, {"action": "check"})):
        ns = argparse.Namespace(**vars(args), **extra)
        ns.json = ns.codequality = None
        codes.append(fn(ns, cfg))
        print()
    return max(codes)


def cmd_rules(args, cfg):
    """Онтология: роли, сущности и каталог правил."""
    from importlib import resources
    onto = yaml.safe_load(resources.files("gitsci.data").joinpath("ontology.yml").read_text(encoding="utf-8"))
    lines = ["# Онтология Git for Science", "", "## Роли", ""]
    for rid, r in onto["roles"].items():
        lines.append(f"### {r['title']} (`{rid}`)")
        lines.append(f"- GitLab: {r['gitlab']}")
        if r.get("sees"):
            lines.append(f"- Видит: {r['sees']}")
        lines += [f"- Может: {c}" for c in r.get("can", [])] + [f"- Не может: {c}" for c in r.get("cannot", [])]
        lines.append("")
    lines += ["## Сущности", ""] + [f"- **{k}** — {v}" for k, v in onto["entities"].items()]
    lines += ["", "Статусы раздела: " + " → ".join(onto["section_statuses"]), "", "## Правила", "",
              "| Правило | Блок | Уровень | Что проверяет |", "|---|---|---|---|"]
    for rid, r in onto["rules"].items():
        lines.append(f"| `{rid}` | {r['block']} | {r['severity']} | {r['text']} |")
    text = "\n".join(lines) + "\n"
    if args.md:
        Path(args.md).parent.mkdir(parents=True, exist_ok=True)
        Path(args.md).write_text(text, encoding="utf-8")
        print(f"Записано: {args.md} ({len(onto['rules'])} правил)")
    else:
        print(text)
    return 0


def cmd_zip(args, cfg):
    form = zipcheck.load_form(args.form)
    report, accepted, _ = zipcheck.check(args.file, form, offline=args.offline,
                                         registry_root=cfg.get("registry") or os.environ.get("GITSCI_REGISTRY"))
    print(zipcheck.verdict_text(report, accepted, Path(args.file).name))
    if args.html:
        Path(args.html).write_text(zipcheck.verdict_html(report, accepted, Path(args.file).name), encoding="utf-8")
    if args.json:
        report.write(args.json, "json")
    return 0 if accepted else 1


def cmd_publish(args, cfg):
    token = os.environ.get("GITHUB_TOKEN")
    report, files, out, status = publish.run(".", args.out, args.version, token, args.dry_run)
    print(report.to_text("Публикация") if report.findings else "Секретов не найдено")
    print(f"Файлов к публикации: {len(files)} → {out}")
    print(status)
    return 1 if report.failed("error") else 0


def cmd_dashboard(args, cfg):
    gl = GitLab()
    if not gl.enabled:
        raise SystemExit("Нужен GITSCI_API_TOKEN")
    projects = dashboard.collect(gl, args.group)
    md = dashboard.markdown(projects)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "dashboard.md").write_text(md, encoding="utf-8")
    (out / "index.html").write_text(dashboard.to_html(md), encoding="utf-8")
    if args.commit_to:
        dashboard.commit_readme(gl, args.commit_to, md)
        print(f"README обновлён в {args.commit_to}")
    print(md)
    return 0


def cmd_profiles(args, cfg):
    print("\n".join(profile.available()))
    return 0


# --- разбор аргументов ------------------------------------------------------------

def main(argv=None):
    p = argparse.ArgumentParser(prog="gitsci", description="Git for Science — проверки научного проекта")
    p.add_argument("--config", default="gitsci.yml")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp, profile_arg=True):
        sp.add_argument("--json", help="сохранить отчёт в JSON")
        sp.add_argument("--codequality", help="сохранить отчёт GitLab Code Quality (виден в MR)")
        sp.add_argument("--fail-on", default="error", choices=["error", "warning", "info"])
        if profile_arg:
            sp.add_argument("--profile", help="профиль формата (lab, scirep или путь к YAML)")
        return sp

    sp = common(sub.add_parser("latex", help="формат + стиль + авторы"))
    sp.add_argument("papers", nargs="*")
    sp.set_defaults(fn=cmd_latex)

    sp = common(sub.add_parser("style", help="только стиль текста"))
    sp.add_argument("papers", nargs="+")
    sp.set_defaults(fn=cmd_style)

    sp = common(sub.add_parser("bib", help="библиография и DOI"))
    sp.add_argument("file", nargs="?")
    sp.add_argument("--offline", action="store_true", help="только кэш, без запросов в Crossref")
    sp.set_defaults(fn=cmd_bib)

    sp = common(sub.add_parser("figures", help="стиль графиков"))
    sp.add_argument("dir", nargs="?")
    sp.set_defaults(fn=cmd_figures)

    sp = common(sub.add_parser("plan", help="план статьи и апрув RU-версии"), profile_arg=False)
    sp.add_argument("file", nargs="?")
    sp.add_argument("--project", help="путь проекта в GitLab, например lab/paper-spsa")
    sp.add_argument("--sync", action="store_true", help="создать/обновить задачи GitLab по plan.yml")
    sp.set_defaults(fn=cmd_plan)

    sp = common(sub.add_parser("registry", help="реестр участников"), profile_arg=False)
    sp.add_argument("root", nargs="?")
    sp.add_argument("--table", help="сгенерировать таблицу (путь без расширения)")
    sp.add_argument("--remind", action="store_true", help="завести задачи по устаревшим записям")
    sp.add_argument("--project", help="проект реестра в GitLab для задач-напоминаний")
    sp.set_defaults(fn=cmd_registry)

    sp = common(sub.add_parser("exp", help="снимки экспериментов"), profile_arg=False)
    sp.add_argument("action", choices=["run", "list", "diff", "check"])
    sp.add_argument("a", nargs="?")
    sp.add_argument("b", nargs="?")
    sp.add_argument("-n", "--name", default="run")
    sp.add_argument("-o", "--output", action="append", help="глоб выходных файлов (можно несколько)")
    sp.add_argument("--note", help="комментарий к запуску")
    sp.set_defaults(fn=cmd_exp)

    sp = common(sub.add_parser("all", help="все проверки проекта"))
    sp.add_argument("--offline", action="store_true")
    sp.set_defaults(fn=cmd_all)

    sub.add_parser("profiles", help="список встроенных профилей").set_defaults(fn=cmd_profiles)

    sp = sub.add_parser("rules", help="онтология: роли и каталог правил")
    sp.add_argument("--md", help="записать в Markdown-файл")
    sp.set_defaults(fn=cmd_rules)

    sp = sub.add_parser("zip", help="проверить архив «по форме» → принят / не принят")
    sp.add_argument("file")
    sp.add_argument("--form", help="своя форма архива (YAML)")
    sp.add_argument("--html", help="сохранить вердикт в HTML")
    sp.add_argument("--json")
    sp.add_argument("--offline", action="store_true")
    sp.set_defaults(fn=cmd_zip)

    sp = sub.add_parser("publish", help="очищенная копия проекта → GitHub")
    sp.add_argument("--version", default="dev")
    sp.add_argument("--out", default="public-export")
    sp.add_argument("--dry-run", action="store_true")
    sp.set_defaults(fn=cmd_publish)

    sp = sub.add_parser("dashboard", help="сводная таблица по проектам (для руководителей)")
    sp.add_argument("--group", default="lab")
    sp.add_argument("--out", default="dashboard-out")
    sp.add_argument("--commit-to", help="проект, в README которого записать сводку")
    sp.set_defaults(fn=cmd_dashboard)

    argv = list(sys.argv[1:] if argv is None else argv)
    tail = []
    if "--" in argv:  # всё после «--» — команда эксперимента, argparse её не трогает
        i = argv.index("--")
        argv, tail = argv[:i], argv[i + 1:]
    args = p.parse_args(argv)
    if args.cmd == "exp":
        args.command = tail
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    return args.fn(args, load_config(args.config))


if __name__ == "__main__":
    sys.exit(main())
