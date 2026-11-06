"""Публикация проекта на GitHub: очищенная копия без внутренней кухни лаборатории.

Что публикуется, задаёт publish.yml в проекте (иначе — DEFAULT). История коммитов не переносится:
на GitHub уходит один коммит «Release <версия>», чтобы черновики, апрувы и обсуждения остались внутри.
Перед отправкой — поиск секретов (токены, ключи); при находке публикация останавливается.
Отправку запускает только руководитель (защищённый тег publish-*), токен GitHub — в переменной группы.
"""

import fnmatch
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import yaml

from .findings import ERROR, Report

DEFAULT = {
    "github": None,  # например: my-lab/adaptive-spsa
    "exclude": [
        "plan.yml", "gitsci.yml", "AGENTS.md", ".claude/*", ".gitlab-ci.yml", "publish.yml",
        "paper/ru/*", "experiments/runs/*/code.patch", "experiments/runs/*/untracked/*",
        "experiments/runs/*/requirements.lock.txt", ".gitsci-cache/*", "*.meta.json",
    ],
    "readme": None,  # отдельный публичный README (например, README.public.md)
}
SECRETS = [
    (r"glpat-[0-9A-Za-z_\-]{20,}", "токен GitLab"),
    (r"gh[pousr]_[0-9A-Za-z]{30,}", "токен GitHub"),
    (r"AKIA[0-9A-Z]{16}", "ключ AWS"),
    (r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----", "приватный ключ"),
    (r"(?i)(api[_-]?key|secret|password)\s*[:=]\s*['\"][^'\"]{8,}['\"]", "пароль/ключ в коде"),
]


def load(path="publish.yml"):
    cfg = dict(DEFAULT)
    if Path(path).exists():
        cfg.update(yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {})
    return cfg


def _tracked_files(root):
    out = subprocess.run(["git", "ls-files"], cwd=root, capture_output=True, text=True, encoding="utf-8")
    if out.returncode == 0 and out.stdout.strip():
        return out.stdout.splitlines()
    return [str(p.relative_to(root)).replace("\\", "/") for p in Path(root).rglob("*") if p.is_file()]


def export(root, out, cfg, report):
    """Копирует разрешённые файлы в out. Возвращает список опубликованных путей."""
    root, out = Path(root), Path(out)
    files = []
    for rel in _tracked_files(root):
        if any(fnmatch.fnmatch(rel, pat) for pat in cfg["exclude"]):
            continue
        src = root / rel
        if not src.is_file():
            continue
        text = None
        if src.stat().st_size < 2_000_000:
            try:
                text = src.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                text = None
        if text is not None:
            for pat, what in SECRETS:
                m = re.search(pat, text)
                if m:
                    line = text.count("\n", 0, m.start()) + 1
                    report.add("PUB_SECRET", ERROR, f"Похоже на {what} — публикация остановлена", rel, line,
                               hint="Уберите секрет из файла и из истории, перевыпустите токен")
        dst = out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        files.append(rel)
    if cfg.get("readme") and (root / cfg["readme"]).exists():
        shutil.copy2(root / cfg["readme"], out / "README.md")
    return files


def push(out, repo, token, version, author="Git for Science"):
    url = f"https://x-access-token:{token}@github.com/{repo}.git"
    env_git = ["git", "-c", f"user.name={author}", "-c", "user.email=gitsci@users.noreply.github.com"]
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=out, check=True)
    subprocess.run(["git", "add", "-A"], cwd=out, check=True)
    subprocess.run([*env_git, "commit", "-q", "-m", f"Release {version}"], cwd=out, check=True)
    subprocess.run(["git", "tag", version], cwd=out, check=True)
    subprocess.run(["git", "push", "-q", "--force", url, "main", version], cwd=out, check=True)


def run(root=".", out=None, version="dev", token=None, dry_run=False):
    cfg = load(Path(root) / "publish.yml")
    report = Report()
    out = Path(out or tempfile.mkdtemp(prefix="gitsci-publish-"))
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    files = export(root, out, cfg, report)
    if report.failed("error"):
        return report, files, out, "остановлено: найдены секреты"
    if not cfg.get("github"):
        return report, files, out, "репозиторий GitHub не задан (publish.yml: github) — только архив"
    if dry_run or not token:
        return report, files, out, f"пробный прогон: ушло бы в github.com/{cfg['github']} ({len(files)} файлов)"
    push(out, cfg["github"], token, version)
    return report, files, out, f"опубликовано: https://github.com/{cfg['github']}/tree/{version}"
