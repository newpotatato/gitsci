"""Проверка .bib: структура записей и соответствие DOI ↔ название через Crossref.

Детерминированно: DOI резолвится в Crossref, название сравнивается нечётко (порог в профиле).
Ответы Crossref кэшируются в .gitsci-cache/crossref.json — повторные прогоны и CI работают быстро,
а с --offline проверка идёт только по кэшу.
"""

import difflib
import json
import os
import re
import unicodedata
from pathlib import Path

import requests

from .findings import ERROR, INFO, WARNING

DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")
REQUIRED = {
    "article": ["author", "title", "journal", "year"],
    "inproceedings": ["author", "title", "booktitle", "year"],
    "book": ["title", "year"],
}
NO_DOI_OK = {"misc", "online", "software", "manual", "techreport", "unpublished"}
CACHE = Path(os.environ.get("GITSCI_CACHE_DIR", ".gitsci-cache")) / "crossref.json"


# --- парсер ------------------------------------------------------------------

def parse(path):
    """Минимальный парсер BibTeX → [{'type', 'key', 'line', 'fields'}]."""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    entries, i = [], 0
    for m in re.finditer(r"@(\w+)\s*\{\s*([^,\s]+)\s*,", text):
        if m.start() < i:
            continue
        kind = m.group(1).lower()
        if kind in ("comment", "string", "preamble"):
            continue
        depth, j = 1, m.end()
        while j < len(text) and depth:
            depth += {"{": 1, "}": -1}.get(text[j], 0)
            j += 1
        body = text[m.end():j - 1]
        entries.append({
            "type": kind,
            "key": m.group(2),
            "line": text.count("\n", 0, m.start()) + 1,
            "fields": _fields(body),
        })
        i = j
    return entries


def _fields(body):
    fields, i = {}, 0
    for m in re.finditer(r"(\w[\w-]*)\s*=\s*", body):
        if m.start() < i:
            continue
        j = m.end()
        if j < len(body) and body[j] == "{":
            depth, k = 0, j
            while k < len(body):
                depth += {"{": 1, "}": -1}.get(body[k], 0)
                k += 1
                if depth == 0:
                    break
            value = body[j + 1:k - 1]
        elif j < len(body) and body[j] == '"':
            k = body.find('"', j + 1) + 1
            value = body[j + 1:k - 1]
        else:
            k = j
            while k < len(body) and body[k] not in ",\n":
                k += 1
            value = body[j:k]
        fields[m.group(1).lower()] = " ".join(value.split())
        i = k
    return fields


# --- нормализация ------------------------------------------------------------

def normalize_title(title):
    title = re.sub(r"\\[A-Za-z]+\s*", " ", title or "")
    title = unicodedata.normalize("NFKD", title)
    title = "".join(ch for ch in title if not unicodedata.combining(ch))
    title = re.sub(r"[^\w\s]", " ", title.lower())
    return " ".join(title.split())


def similarity(a, b):
    a, b = normalize_title(a), normalize_title(b)
    if not a or not b:
        return 0.0
    ratio = difflib.SequenceMatcher(None, a, b).ratio()
    sa, sb = set(a.split()), set(b.split())
    jaccard = len(sa & sb) / len(sa | sb)
    return max(ratio, jaccard)


def normalize_doi(doi):
    doi = (doi or "").strip()
    return re.sub(r"^(https?://)?(dx\.)?doi\.org/|^doi:\s*", "", doi, flags=re.I)


# --- Crossref ----------------------------------------------------------------

class Crossref:
    def __init__(self, offline=False, cache_path=CACHE):
        self.offline = offline
        self.cache_path = Path(cache_path)
        self.cache = json.loads(self.cache_path.read_text(encoding="utf-8")) if self.cache_path.exists() else {}
        mailto = os.environ.get("GITSCI_MAILTO", "")
        self.headers = {"User-Agent": "gitsci/0.1" + (f" (mailto:{mailto})" if mailto else "")}
        self.dirty = False

    def work(self, doi):
        """Метаданные по DOI: dict, None (DOI не существует) или 'unknown' (нет сети и кэша)."""
        key = doi.lower()
        if key in self.cache:
            return self.cache[key]
        if self.offline:
            return "unknown"
        try:
            r = requests.get(f"https://api.crossref.org/works/{requests.utils.quote(doi)}",
                             headers=self.headers, timeout=20)
        except requests.RequestException:
            return "unknown"
        if r.status_code == 404:
            result = None
        elif r.ok:
            msg = r.json()["message"]
            result = {
                "title": (msg.get("title") or [""])[0],
                "year": _year(msg),
                "first_author": ((msg.get("author") or [{}])[0]).get("family", ""),
                "container": (msg.get("container-title") or [""])[0],
            }
        else:
            return "unknown"
        self.cache[key] = result
        self.dirty = True
        return result

    def search(self, title):
        if self.offline:
            return None
        try:
            r = requests.get("https://api.crossref.org/works", params={"query.bibliographic": title, "rows": 1},
                             headers=self.headers, timeout=20)
            items = r.json()["message"]["items"] if r.ok else []
        except (requests.RequestException, ValueError, KeyError):
            return None
        if items and similarity(title, (items[0].get("title") or [""])[0]) >= 0.9:
            return items[0]["DOI"]
        return None

    def save(self):
        if self.dirty:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(json.dumps(self.cache, ensure_ascii=False, indent=1), encoding="utf-8")


def _year(msg):
    for k in ("published-print", "published-online", "issued"):
        parts = (msg.get(k) or {}).get("date-parts") or [[None]]
        if parts[0][0]:
            return int(parts[0][0])
    return None


# --- проверка ----------------------------------------------------------------

def check(bib_path, report, cfg, offline=False, crossref=None):
    rel = str(bib_path).replace("\\", "/")
    entries = parse(bib_path)
    threshold = cfg.get("title_match_threshold", 0.85)
    cr = crossref or Crossref(offline=offline)

    seen = {}
    for e in entries:
        key, f, line = e["key"], e["fields"], e["line"]
        if key in seen:
            report.add("BIB_DUPLICATE_KEY", ERROR, f"Ключ {key} повторяется (первый раз в строке {seen[key]})",
                       rel, line)
            continue
        seen[key] = line
        for name in REQUIRED.get(e["type"], []):
            if not f.get(name):
                report.add("BIB_FIELD_MISSING", WARNING, f"{key}: нет поля {name}", rel, line)

        doi = normalize_doi(f.get("doi"))
        if not doi:
            if cfg.get("require_doi", True) and e["type"] not in NO_DOI_OK:
                found = cr.search(f.get("title", "")) if f.get("title") else None
                report.add("BIB_DOI_MISSING", WARNING, f"{key}: нет DOI", rel, line,
                           f"Найден в Crossref: {found}" if found else "Добавьте поле doi")
            continue
        if not DOI_RE.match(doi):
            report.add("BIB_DOI_MALFORMED", ERROR, f"{key}: некорректный DOI «{doi}»", rel, line,
                       "Формат: 10.XXXX/суффикс, без https://doi.org/")
            continue

        meta = cr.work(doi)
        if meta == "unknown":
            report.add("BIB_DOI_UNCHECKED", INFO, f"{key}: DOI не проверен (нет сети/кэша)", rel, line)
            continue
        if meta is None:
            report.add("BIB_DOI_NOT_FOUND", ERROR, f"{key}: DOI {doi} не существует в Crossref", rel, line)
            continue
        score = similarity(f.get("title", ""), meta["title"])
        if score < threshold:
            report.add("BIB_DOI_TITLE_MISMATCH", ERROR,
                       f"{key}: DOI ведёт на другую статью (совпадение {score:.0%})", rel, line,
                       f"По DOI: «{meta['title'][:90]}»")
            continue
        year = f.get("year", "")
        if meta.get("year") and year.isdigit() and abs(int(year) - meta["year"]) > 1:
            report.add("BIB_YEAR_MISMATCH", WARNING, f"{key}: год {year}, в Crossref {meta['year']}", rel, line)
        surname = normalize_title(meta.get("first_author", ""))
        authors = normalize_title(f.get("author", ""))
        if surname and authors and surname.split()[-1] not in authors:
            report.add("BIB_AUTHOR_MISMATCH", WARNING,
                       f"{key}: первый автор по DOI — {meta['first_author']}, в .bib его нет", rel, line)
    cr.save()
    return {e["key"] for e in entries}
