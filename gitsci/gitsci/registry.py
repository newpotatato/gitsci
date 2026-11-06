"""Реестр участников лаборатории (таблица на схеме) и сверка авторов статьи с ним.

Реестр — папка с YAML-файлами, по одному на человека (репозиторий lab-registry).
Проверяется формат идентификаторов (ORCID с контрольной суммой, Scopus, РИНЦ, WoS, почта)
и свежесть записи: актуализация раз в 6 месяцев.
"""

import difflib
import html
import re
from datetime import date
from pathlib import Path

import yaml

from .findings import ERROR, INFO, WARNING

STALE_DAYS = 183
REQUIRED = ["id", "name_ru", "name_en", "email", "affiliations", "updated"]
FORMATS = {
    "email": (re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$"), "ivanov@uni.ru"),
    "telegram": (re.compile(r"^@[A-Za-z0-9_]{5,32}$"), "@username"),
    "scopus_id": (re.compile(r"^\d{10,11}$"), "10–11 цифр"),
    "rinc_id": (re.compile(r"^\d{4,8}(-\d{4})?$"), "AuthorID (цифры) или SPIN 1234-5678"),
    "wos_id": (re.compile(r"^[A-Z]{1,3}-\d{4}-\d{4}$"), "ResearcherID вида A-1234-2019"),
    "linkedin": (re.compile(r"^https://(www\.)?linkedin\.com/in/[\w-]+/?$"), "https://www.linkedin.com/in/имя"),
    "orcid": (re.compile(r"^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$"), "0000-0002-1825-0097"),
}
COLUMNS = [
    ("name_ru", "ФИО рус"), ("name_en", "ФИ англ"), ("telegram", "tg"), ("orcid", "ORCID"),
    ("email", "Почта"), ("affiliations", "Аффилиации"), ("scopus_id", "Scopus ID"), ("rinc_id", "РИНЦ ID"),
    ("wos_id", "WoS ID"), ("linkedin", "LinkedIn"), ("cv", "CV рус/англ"), ("bibliography", "Библиография"),
    ("updated", "Актуализация"),
]


def orcid_valid(orcid):
    """Контрольная сумма ORCID (ISO 7064 Mod 11-2)."""
    digits = orcid.replace("-", "")
    total = 0
    for ch in digits[:-1]:
        total = (total + int(ch)) * 2
    check = (12 - total % 11) % 11
    return digits[-1] == ("X" if check == 10 else str(check))


def load(root):
    people = []
    for path in sorted(Path(root).glob("people/*.y*ml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        data["_file"] = str(path).replace("\\", "/")
        people.append(data)
    return people


def check(root, report, today=None):
    today = today or date.today()
    people = load(root)
    if not people:
        report.add("REG_EMPTY", ERROR, "В реестре нет ни одного файла people/*.yml", str(root))
    ids, gitlabs = {}, {}
    for p in people:
        f = p["_file"]
        for name in REQUIRED:
            if not p.get(name):
                report.add("REG_FIELD_MISSING", ERROR, f"{p.get('id', f)}: нет поля {name}", f)
        if p.get("id") in ids:
            report.add("REG_DUPLICATE_ID", ERROR, f"id {p['id']} уже есть в {ids[p['id']]}", f)
        ids.setdefault(p.get("id"), f)
        if p.get("gitlab"):
            if p["gitlab"] in gitlabs:
                report.add("REG_DUPLICATE_GITLAB", ERROR, f"gitlab {p['gitlab']} уже у {gitlabs[p['gitlab']]}", f)
            gitlabs[p["gitlab"]] = p.get("id")

        for name, (rx, example) in FORMATS.items():
            value = str(p.get(name) or "").strip()
            if value and not rx.match(value):
                report.add("REG_FORMAT", ERROR, f"{p.get('id')}: {name} «{value}» в неверном формате",
                           f, hint=f"Пример: {example}")
        if p.get("orcid") and FORMATS["orcid"][0].match(str(p["orcid"])) and not orcid_valid(str(p["orcid"])):
            report.add("REG_ORCID_CHECKSUM", ERROR, f"{p.get('id')}: ORCID {p['orcid']} с неверной контрольной суммой",
                       f, hint="Скопируйте ORCID с orcid.org — скорее всего, опечатка")
        for i, aff in enumerate(p.get("affiliations") or [], 1):
            if not isinstance(aff, dict) or not aff.get("name_en") or not aff.get("name_ru"):
                report.add("REG_AFFILIATION", ERROR, f"{p.get('id')}: аффилиация {i} без name_ru/name_en", f)
        for name in ("orcid", "scopus_id", "rinc_id"):
            if not p.get(name):
                report.add("REG_ID_MISSING", WARNING, f"{p.get('id')}: не заполнен {name}", f)
        for lang in ("ru", "en"):
            cv = (p.get("cv") or {}).get(lang)
            if not cv:
                report.add("REG_CV_MISSING", INFO, f"{p.get('id')}: нет CV/биографии ({lang})", f)
            elif not str(cv).startswith("http") and not (Path(root) / cv).exists():
                report.add("REG_CV_FILE", ERROR, f"{p.get('id')}: файл CV не найден: {cv}", f)

        updated = p.get("updated")
        if isinstance(updated, str):
            try:
                updated = date.fromisoformat(updated)
            except ValueError:
                report.add("REG_FORMAT", ERROR, f"{p.get('id')}: updated должна быть датой ГГГГ-ММ-ДД", f)
                updated = None
        if isinstance(updated, date) and (today - updated).days > STALE_DAYS:
            report.add("REG_STALE", WARNING,
                       f"{p.get('id')}: запись не актуализировалась {(today - updated).days} дн. (раз в 6 мес)",
                       f, hint="Проверьте аффилиации, ID и библиографию, обновите поле updated")
    return people


def remind(people, gl, project, today=None):
    """Задача «актуализируйте запись» владельцу каждой записи старше 6 месяцев (без дублей)."""
    today = today or date.today()
    pid = gl.pid(project)
    open_titles = {i["title"] for i in gl.get_all(f"projects/{pid}/issues", state="opened")}
    created = []
    for p in people:
        upd = p.get("updated")
        upd = date.fromisoformat(upd) if isinstance(upd, str) else upd
        if not isinstance(upd, date) or (today - upd).days <= STALE_DAYS:
            continue
        title = f"Актуализировать запись: {p.get('name_ru')}"
        if title in open_titles:
            continue
        user = gl.get("users", username=p.get("gitlab")) if p.get("gitlab") else []
        issue = gl.post(
            f"projects/{pid}/issues", title=title, labels="registry,актуализация", confidential=True,
            assignee_ids=[user[0]["id"]] if user else [],
            due_date=str(date.fromordinal(today.toordinal() + 14)),
            description=(f"Запись `{p.get('_file')}` не обновлялась с {upd}.\n\n"
                         "- [ ] аффилиации и рабочая почта\n- [ ] Scopus / РИНЦ / WoS / ORCID\n"
                         "- [ ] CV рус/англ\n- [ ] библиография\n- [ ] поле `updated`"),
        )
        created.append(issue["web_url"])
    return created


# --- таблица -------------------------------------------------------------------

def _cell(p, key):
    v = p.get(key)
    if key == "affiliations":
        return "; ".join(f"{a.get('name_ru', '')} ({a.get('email', '')})".replace(" ()", "")
                         for a in (v or []) if isinstance(a, dict))
    if key == "cv":
        return " / ".join(str((v or {}).get(lang, "—")) for lang in ("ru", "en"))
    if key == "bibliography":
        return f"{len(v)} публ." if isinstance(v, list) else (str(v) if v else "—")
    return str(v) if v else "—"


def table_markdown(people):
    head = "| " + " | ".join(t for _, t in COLUMNS) + " |"
    sep = "|" + "---|" * len(COLUMNS)
    rows = ["| " + " | ".join(_cell(p, k).replace("|", "/") for k, _ in COLUMNS) + " |" for p in people]
    return "\n".join([head, sep, *rows]) + "\n"


def table_html(people, today=None):
    today = today or date.today()
    head = "".join(f"<th>{html.escape(t)}</th>" for _, t in COLUMNS)
    rows = []
    for p in people:
        upd = p.get("updated")
        upd = date.fromisoformat(upd) if isinstance(upd, str) else upd
        stale = isinstance(upd, date) and (today - upd).days > STALE_DAYS
        cells = "".join(f"<td>{html.escape(_cell(p, k))}</td>" for k, _ in COLUMNS)
        rows.append(f"<tr class='{'stale' if stale else ''}'>{cells}</tr>")
    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>Реестр участников</title>
<style>body{{font:14px system-ui,sans-serif;margin:24px;color:#1d1d1f}}table{{border-collapse:collapse}}
th,td{{border:1px solid #ddd;padding:6px 8px;vertical-align:top}}th{{background:#f5f5f7;text-align:left}}
tr.stale td{{background:#fff4e5}}caption{{text-align:left;margin-bottom:8px;color:#666}}</style></head><body>
<h1>Реестр участников лаборатории</h1><table><caption>Оранжевым — записи старше 6 месяцев. Сформировано {today}.</caption>
<thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table></body></html>"""


# --- сверка авторов статьи --------------------------------------------------------

def _norm(name):
    return " ".join(re.sub(r"[^\wА-Яа-яЁё\s-]", " ", name).lower().replace("ё", "е").split())


def paper_authors(doc):
    """Авторы из LaTeX: формат sn-jnl (\\fnm/\\sur) или обычный \\author{A \\and B}."""
    out = []
    for off, arg in doc.commands("author"):
        fnm = re.search(r"\\fnm\{([^}]*)\}", arg)
        sur = re.search(r"\\sur\{([^}]*)\}", arg)
        if fnm or sur:
            out.append((off, f"{fnm.group(1) if fnm else ''} {sur.group(1) if sur else ''}".strip()))
            continue
        for part in re.split(r"\\and|,", arg):
            name = re.sub(r"\\[A-Za-z]+\s*(\{[^}]*\})?|\$[^$]*\$|[\d*{}^]", " ", part)
            if name.strip():
                out.append((off, " ".join(name.split())))
    return out


def check_paper_authors(doc, people, report, today=None):
    today = today or date.today()
    lang = doc.language()
    by_name = {}
    for p in people:
        for key in ("name_en", "name_ru"):
            if p.get(key):
                full = _norm(p[key])
                by_name[full] = p
                parts = full.split()
                if key == "name_ru" and len(parts) == 3:  # без отчества
                    by_name[f"{parts[1]} {parts[0]}"] = p
                    by_name[f"{parts[0]} {parts[1]}"] = p
                if len(parts) >= 2:
                    by_name[f"{parts[-1]} {parts[0]}"] = p

    matched = []
    for off, name in paper_authors(doc):
        file, line = doc.locate(off)
        n = _norm(name)
        if n in by_name:
            matched.append(by_name[n])
            continue
        close = difflib.get_close_matches(n, list(by_name), n=1, cutoff=0.75)
        if close:
            right = by_name[close[0]]["name_en" if lang == "en" else "name_ru"]
            report.add("AUTH_NAME_SPELLING", ERROR, f"Автор «{name}» написан не как в реестре", doc.rel(file), line,
                       f"В реестре: «{right}»")
            matched.append(by_name[close[0]])
        else:
            report.add("AUTH_NOT_IN_REGISTRY", WARNING, f"Автора «{name}» нет в реестре лаборатории",
                       doc.rel(file), line, "Внешний соавтор — ок; свой — добавьте в lab-registry")

    emails = {e.lower() for p in matched for e in [p.get("email")] +
              [a.get("email") for a in p.get("affiliations") or [] if isinstance(a, dict)] if e}
    for off, mail in doc.commands("email"):
        if matched and mail.strip().lower() not in emails:
            file, line = doc.locate(off)
            report.add("AUTH_EMAIL", WARNING, f"Почта {mail.strip()} не совпадает с реестром", doc.rel(file), line)

    affs = [a for p in matched for a in p.get("affiliations") or [] if isinstance(a, dict)]
    for off, arg in doc.commands("affil"):
        text = _norm(re.sub(r"\\[A-Za-z]+", " ", arg))
        if affs and not any(_norm(a.get("name_en", "")) in text or _norm(a.get("name_ru", "")) in text for a in affs):
            file, line = doc.locate(off)
            report.add("AUTH_AFFILIATION", WARNING, "Аффилиация не совпадает ни с одной из реестра авторов",
                       doc.rel(file), line, "Варианты: " + "; ".join(a.get("name_en", "") for a in affs))

    for p in matched:
        upd = p.get("updated")
        upd = date.fromisoformat(upd) if isinstance(upd, str) else upd
        if isinstance(upd, date) and (today - upd).days > STALE_DAYS:
            report.add("AUTH_REGISTRY_STALE", WARNING,
                       f"Данные автора {p.get('name_en')} в реестре устарели ({upd})", p.get("_file", ""))
