"""Загрузка профилей формата: встроенные (lab, scirep) или свой YAML-файл."""

from importlib import resources
from pathlib import Path

import yaml


def available():
    return sorted(p.name[:-4] for p in resources.files("gitsci.profiles").iterdir() if p.name.endswith(".yml"))


def load(name_or_path):
    path = Path(name_or_path)
    if path.suffix in (".yml", ".yaml") and path.is_file():
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    res = resources.files("gitsci.profiles").joinpath(f"{name_or_path}.yml")
    if not res.is_file():
        raise SystemExit(f"Профиль «{name_or_path}» не найден. Встроенные: {', '.join(available())}")
    return yaml.safe_load(res.read_text(encoding="utf-8")) or {}
