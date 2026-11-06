"""Стилевые правила лаборатории (блок PROBLEMS на схеме).

Все правила детерминированные: регулярные выражения и словари, без LLM.
Каждое правило можно выключить или сменить уровень в профиле (`style:` в YAML).
"""

import re
from importlib import resources

from ..findings import ERROR, WARNING

_SENTENCE_END = re.compile(r"[.!?…]\s|\n\s*\n")
_OPERATOR_ONLY = re.compile(r"^(=|\+|-|\\cdot|\\times|<|>|\\le|\\ge|\\leq|\\geq|\\approx|\\pm|,|&=|&)$")

# «Избыточные противопоставления»: конструкции «не X, а Y», которые LLM вставляют для «драматизма».
CONTRAST_PATTERNS = {
    "ru": [
        r"\bне\s+только\b[^.;!?]{0,120}?\bно\s+и\b",
        r"\bне\s+просто\b[^.;!?]{0,120}?,\s*а\b",
        r"\bне\s+(?:столько|сколько)\b",
        r"\bне\s+\w+(?:\s+\w+){0,4},\s*а\s+(?!также\b)",
        r",\s*а\s+не\b",
        r"\bвместо\s+того\s+чтобы\b",
        r"\bдело\s+не\s+в\b",
        r"\bэто\s+не\b[^.;!?]{0,60}?\s[—–-]{1,3}\s*это\b",
    ],
    "en": [
        r"\bnot\s+only\b[^.;!?]{0,120}?\bbut\s+(?:also\b)?",
        r"\bnot\s+(?:just|merely|simply)\b[^.;!?]{0,120}?\bbut\b",
        r"\bnot\s+\w+(?:\s+\w+){0,4},\s*but\b",
        r"\brather\s+than\b",
        r"\b(?:isn't|is\s+not|aren't|are\s+not)\b[^.;!?]{0,60}?[;,—–-]+\s*(?:it|they)(?:'s|\s+is|\s+are)\b",
        r"\bit'?s\s+not\s+about\b",
    ],
}


def _load_words(lang):
    text = resources.files("gitsci.data").joinpath(f"water_{lang}.txt").read_text(encoding="utf-8")
    words = [w.strip() for w in text.splitlines() if w.strip() and not w.startswith("#")]
    return sorted(words, key=len, reverse=True)


def _sentences(prose):
    """Границы предложений в прозе: [(start, end)]."""
    out, start = [], 0
    for m in _SENTENCE_END.finditer(prose):
        out.append((start, m.end()))
        start = m.end()
    out.append((start, len(prose)))
    return out


def _level(cfg, name, default):
    value = cfg.get(name, default)
    if value is False or value == "off":
        return None
    return value if value in (ERROR, WARNING, "info") else default


def check(doc, report, cfg):
    lang = doc.language()
    prose = doc.prose

    def add(rule, sev, offset, message, hint=""):
        file, line = doc.locate(offset)
        report.add(rule, sev, message, doc.rel(file), line, hint)

    # --- точка с запятой в прозе ------------------------------------------
    sev = _level(cfg, "semicolon", ERROR)
    if sev:
        for m in re.finditer(r";", prose):
            add("STYLE_SEMICOLON", sev, m.start(), "«;» в тексте запрещена",
                "Разбейте на два предложения или перечислите через запятую/список")

    # --- тире ----------------------------------------------------------------
    sev = _level(cfg, "triple_dash", ERROR)
    if sev:
        for m in re.finditer(r"---|—", prose):
            add("STYLE_TRIPLE_DASH", sev, m.start(), "Длинное тире («---» / «—») в тексте запрещено",
                "Перестройте фразу: двоеточие, скобки или отдельное предложение")
    sev = _level(cfg, "paired_dash", ERROR)
    if sev:
        dash = re.compile(r"(?<![\d-])(?:\s[-–—]{1,3}\s|---|—|(?<=\w)--(?=\s)|\s--(?=\w))")
        for s, e in _sentences(prose):
            hits = list(dash.finditer(prose, s, e))
            if len(hits) >= 2:
                add("STYLE_PAIRED_DASH", sev, hits[0].start(),
                    "Конструкция с двумя тире внутри одного предложения («X – вставка – Y»)",
                    "Вынесите вставку в скобки или в отдельное предложение")

    # --- противопоставления --------------------------------------------------
    sev = _level(cfg, "contrast", WARNING)
    if sev:
        found, seen = 0, set()
        for pat in CONTRAST_PATTERNS[lang]:
            for m in re.finditer(pat, prose, re.I):
                if any(a <= m.start() < b or m.start() <= a < m.end() for a, b in seen):
                    continue  # тот же оборот поймали другим шаблоном
                seen.add((m.start(), m.end()))
                found += 1
                snippet = " ".join(prose[m.start():m.end()].split())
                add("STYLE_CONTRAST", sev, m.start(), f"Противопоставление: «{snippet[:60]}»",
                    "Скажите утверждение прямо, без «не X, а Y»")
        words = max(len(prose.split()), 1)
        limit = cfg.get("contrast_per_1000_words", 2)
        if found / words * 1000 > limit:
            report.add("STYLE_CONTRAST_DENSITY", WARNING,
                       f"Противопоставлений {found} на {words} слов (порог {limit} на 1000)",
                       doc.rel(doc.root))

    # --- «вода» -------------------------------------------------------------
    sev = _level(cfg, "water", WARNING)
    if sev:
        found = 0
        for phrase in _load_words(lang):
            for m in re.finditer(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", prose, re.I):
                found += 1
                add("STYLE_WATER", sev, m.start(), f"«Вода»: «{phrase}»", "Удалите или замените конкретикой")
        words = max(len(prose.split()), 1)
        limit = cfg.get("water_per_1000_words", 5)
        if found / words * 1000 > limit:
            report.add("STYLE_WATER_DENSITY", WARNING,
                       f"Водных оборотов {found} на {words} слов (порог {limit} на 1000)", doc.rel(doc.root))

    # --- формулы ------------------------------------------------------------
    sev = _level(cfg, "fragmented_equation", ERROR)
    for env, a, b in doc.math_blocks:
        body = doc.text[a:b]
        rows = [r.strip() for r in body.split("\n")]
        if any(r == "" for r in rows[1:-1]) and sev:
            add("EQ_BLANK_LINE", ERROR, a, f"Пустая строка внутри окружения {env}", "В формуле не должно быть пустых строк")
        nonempty = [r for r in rows if r]
        if not sev or len(nonempty) < 4:
            continue
        operators = sum(1 for r in nonempty if _OPERATOR_ONLY.match(r))
        tiny = sum(1 for r in nonempty if len(r) <= 4)
        intentional = sum(1 for r in nonempty if r.endswith("\\\\"))
        if operators >= 1 and not intentional or operators >= 2 or tiny / len(nonempty) >= 0.6:
            add("EQ_FRAGMENTED", sev, a,
                f"Формула ({env}) разорвана на {len(nonempty)} строк по одному токену",
                "Пишите формулу одной строкой; переносы — только по смыслу (\\\\ в align)")

    # --- табуляция ----------------------------------------------------------
    sev = _level(cfg, "tabs", WARNING)
    if sev:
        per_file = {}
        for ln in doc.lines:
            if "\t" in ln.raw:
                per_file.setdefault(ln.file, []).append(ln.no)
        for file, nums in per_file.items():
            report.add("TEX_TABS", sev, f"Табуляция в {len(nums)} строках", doc.rel(file), nums[0],
                       "Используйте пробелы (2 на уровень); latexindent приведёт файл в порядок")
