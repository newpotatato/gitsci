"""Соответствие статьи профилю формата (Example format / Guide / Rules на схеме).

Профиль — YAML в gitsci/profiles/ или путь к своему файлу. Здесь только детерминированные проверки
структуры: класс документа, пакеты, разделы, аннотация, ключевые слова, рисунки, ссылки на метки.
"""

import re
from datetime import date
from pathlib import Path

from ..findings import ERROR, INFO, WARNING
from .texdoc import read_group


def _words(text):
    return len(re.findall(r"[\wА-Яа-яЁё-]+", text))


def _plain(text):
    """Грубо снимает LaTeX-разметку для подсчёта слов."""
    text = re.sub(r"\$.*?\$", " formula ", text, flags=re.S)
    text = re.sub(r"\\[A-Za-z@]+\*?(\[[^\]]*\])?", " ", text)
    return re.sub(r"[{}~\\]", " ", text)


def check(doc, report, profile, bib_keys=None):
    def add(rule, sev, offset, message, hint=""):
        if offset is None:
            report.add(rule, sev, message, doc.rel(doc.root), 0, hint)
        else:
            file, line = doc.locate(offset)
            report.add(rule, sev, message, doc.rel(file), line, hint)

    # --- класс и пакеты -------------------------------------------------------
    classes = doc.commands("documentclass")
    allowed = profile.get("documentclass")
    if not classes:
        add("FMT_DOCCLASS", ERROR, None, "Нет \\documentclass")
    elif allowed and classes[0][1].strip() not in allowed:
        add("FMT_DOCCLASS", ERROR, classes[0][0],
            f"Класс «{classes[0][1]}» не из разрешённых: {', '.join(allowed)}")

    used = {}
    for off, arg in doc.commands("usepackage"):
        for name in arg.split(","):
            used[name.strip()] = off
    for pkg in profile.get("required_packages", []):
        if pkg not in used:
            add("FMT_PACKAGE_MISSING", ERROR, None, f"Не подключён обязательный пакет {pkg}")
    for pkg in profile.get("forbidden_packages", []):
        if pkg in used:
            add("FMT_PACKAGE_FORBIDDEN", ERROR, used[pkg], f"Пакет {pkg} запрещён профилем")

    # --- заголовок, аннотация, ключевые слова ---------------------------------------
    titles = doc.commands("title")
    limit = profile.get("title_max_words")
    if not titles:
        add("FMT_TITLE", ERROR, None, "Нет \\title")
    elif limit and _words(_plain(titles[0][1])) > limit:
        add("FMT_TITLE", WARNING, titles[0][0],
            f"Заголовок {_words(_plain(titles[0][1]))} слов при пределе {limit}")

    abs_cfg = profile.get("abstract", {})
    abstracts = doc.environments("abstract") or [(o, a) for o, a in doc.commands("abstract")]
    if abs_cfg.get("required", True) and not abstracts:
        add("FMT_ABSTRACT", ERROR, None, "Нет аннотации (abstract)")
    elif abstracts:
        n = _words(_plain(abstracts[0][1]))
        if abs_cfg.get("max_words") and n > abs_cfg["max_words"]:
            add("FMT_ABSTRACT_LENGTH", ERROR, abstracts[0][0],
                f"Аннотация {n} слов при пределе {abs_cfg['max_words']}")
        elif abs_cfg.get("min_words") and n < abs_cfg["min_words"]:
            add("FMT_ABSTRACT_LENGTH", WARNING, abstracts[0][0],
                f"Аннотация {n} слов, нужно не меньше {abs_cfg['min_words']}")
    if abstracts:
        off, body = abstracts[0]
        start = doc.text.find(body, off)  # каждое нарушение — на своей строке
        if abs_cfg.get("no_citations"):
            for m in re.finditer(r"\\cite\w*\s*[\[{]", body):
                add("FMT_ABSTRACT_CITE", ERROR, start + m.start(), "В аннотации есть ссылка на литературу",
                    "Аннотация читается отдельно от статьи: назовите работу словами")
        if abs_cfg.get("no_math"):
            for m in re.finditer(r"\$+[^$]+\$+|\\\(|\\\[|\\begin\{(equation|align)", body):
                add("FMT_ABSTRACT_MATH", WARNING, start + m.start(), "В аннотации есть формула",
                    "Замените формулу словесным описанием")

    kw_cfg = profile.get("keywords")
    if kw_cfg:
        kws = doc.commands(kw_cfg.get("command", "keywords")) or doc.environments("keywords")
        if not kws:
            add("FMT_KEYWORDS", ERROR, None, "Нет ключевых слов (\\keywords)")
        else:
            items = [k for k in re.split(r"[,;]|\\sep", kws[0][1]) if k.strip()]
            if not kw_cfg.get("min", 0) <= len(items) <= kw_cfg.get("max", 99):
                add("FMT_KEYWORDS", WARNING, kws[0][0],
                    f"Ключевых слов {len(items)}, нужно {kw_cfg.get('min', 0)}–{kw_cfg.get('max', '∞')}")
            raw = kws[0][1].strip()
            if kw_cfg.get("comma_separated") and (";" in raw or "\\sep" in raw or raw.endswith(".")):
                add("FMT_KEYWORDS_FORMAT", WARNING, kws[0][0],
                    "Ключевые слова нужно разделять запятыми, без точки в конце")

    # --- разделы --------------------------------------------------------------
    sec_cfg = profile.get("sections", {})
    found = [(off, _plain(t).strip()) for off, t in doc.commands("section")]
    titles_lower = [t.lower() for _, t in found]
    positions = []
    for group in sec_cfg.get("required", []):
        names = [g.lower() for g in ([group] if isinstance(group, str) else group)]
        idx = next((i for i, t in enumerate(titles_lower) if any(t.startswith(n) for n in names)), None)
        if idx is None:
            add("FMT_SECTION_MISSING", ERROR, None, f"Нет обязательного раздела «{names[0].title()}»",
                "Варианты названия: " + ", ".join(names))
        else:
            positions.append((idx, names[0]))
    if sec_cfg.get("ordered") and positions != sorted(positions):
        add("FMT_SECTION_ORDER", WARNING, None,
            "Порядок разделов не совпадает с профилем: " + " → ".join(n for _, n in positions))

    # Заявления (финансирование, конфликт интересов, ИИ...) — в любом месте и любом уровне заголовка.
    heads = [_plain(t).strip().lower() for name in ("section", "subsection", "paragraph", "bmhead")
             for _, t in doc.commands(name)]
    for group in profile.get("declarations", []):
        names = [g.lower() for g in ([group] if isinstance(group, str) else group)]
        if not any(h.startswith(n) for h in heads for n in names):
            add("FMT_DECLARATION_MISSING", ERROR, None, f"Нет заявления «{names[0].capitalize()}»",
                "Варианты заголовка: " + ", ".join(names))

    # --- формулы -------------------------------------------------------------
    wrappers = re.findall(r"\\(?:re)?newcommand\*?\{?\\(\w+)\}?\[\d\](?:\[[^\]]*\])?\{[^\n]*?\\\w*ref\*?\{#1\}", doc.text)
    refs = {arg.strip() for name in ("ref", "eqref", "autoref", "cref", "Cref", *wrappers) for _, a in doc.commands(name)
            for arg in a.split(",")}
    if profile.get("equations", {}).get("number_only_referenced"):
        prose = _prose_without_math(doc)
        for off, number, labels in _numbered_rows(doc):
            if any(lab in refs for lab in labels) or _cited_by_number(prose, number):
                continue
            add("FMT_EQ_UNREFERENCED", WARNING, off, f"Формула ({number}) пронумерована, но на неё нет ссылки",
                "Используйте окружение со звёздочкой или \\nonumber, если ссылка не нужна")

    # --- объём (по .log последней сборки) ----------------------------------------
    pages_cfg = profile.get("pages")
    if pages_cfg:
        log = Path(doc.root).with_suffix(".log")
        m = re.search(r"Output written on .*?\((\d+) pages?", log.read_text(errors="replace")) if log.is_file() else None
        if not m:
            add("FMT_PAGES", INFO, None, "Объём не проверен: нет .log сборки PDF", "Соберите PDF (задание pdf в CI)")
        elif not pages_cfg.get("min", 0) <= int(m.group(1)) <= pages_cfg.get("max", 10 ** 6):
            add("FMT_PAGES", ERROR, None,
                f"Статья {m.group(1)} стр., нужно {pages_cfg.get('min', 0)}–{pages_cfg.get('max', '∞')}")

    # --- рисунки и метки ------------------------------------------------------
    fig_cfg = profile.get("figures", {})
    for off, body in doc.environments("figure") + doc.environments("figure*"):
        if fig_cfg.get("require_caption", True) and "\\caption" not in body:
            add("FMT_FIGURE_CAPTION", ERROR, off, "У рисунка нет подписи (\\caption)")
        labels = re.findall(r"\\label\{([^}]+)\}", body)
        if fig_cfg.get("require_label", True) and not labels:
            add("FMT_FIGURE_LABEL", ERROR, off, "У рисунка нет \\label")
        if labels and fig_cfg.get("require_reference", True) and not refs.intersection(labels):
            add("FMT_FIGURE_UNREFERENCED", WARNING, off, f"На рисунок {labels[0]} нет ссылки в тексте")
        for m in re.finditer(r"\\includegraphics\s*(\[[^\]]*\])?\s*\{", body):
            path, _ = read_group(body, m.end() - 1)
            _check_graphic(doc, path.strip(), fig_cfg, lambda r, s, msg, h="": add(r, s, off, msg, h))

    labels = {lab for _, lab in doc.commands("label")}
    for off, arg in [(o, a) for name in ("ref", "eqref") for o, a in doc.commands(name)]:
        for key in arg.split(","):
            if key.strip() not in labels and "#" not in key:
                add("FMT_REF_UNDEFINED", ERROR, off, f"Ссылка на несуществующую метку {key.strip()}")

    # --- цитирования ----------------------------------------------------------
    if bib_keys is not None:
        cited = {}
        for name in CITE_CMDS + ("nocite",):
            for off, arg in doc.commands(name):
                for key in arg.split(","):
                    cited.setdefault(key.strip(), off)
        for key, off in cited.items():
            if key and key != "*" and key not in bib_keys:
                add("FMT_CITE_UNDEFINED", ERROR, off, f"Цитата {key} отсутствует в .bib")
        for key in sorted(set(bib_keys) - set(cited)):
            add("FMT_BIB_UNUSED", INFO, None, f"Запись {key} из .bib нигде не цитируется")

    if profile.get("references", {}).get("order") == "citation":
        _check_cite_order(doc, add)

    # --- запрещённые конструкции ----------------------------------------------
    for rule in profile.get("forbidden", []):
        for m in re.finditer(rule["pattern"], doc.text):
            add("FMT_FORBIDDEN", rule.get("severity", WARNING), m.start(), rule["message"], rule.get("hint", ""))


NUMBERED_ENVS = "equation|multline|align|gather|eqnarray|flalign|alignat"
INNER_ENVS = r"\w*matrix\*?|cases|array|split|aligned|gathered|alignedat"


def _blank_comments(text):
    """Комментарии заменяются пробелами той же длины: смещения для номеров строк не меняются."""
    return re.sub(r"(?<!\\)%.*", lambda m: " " * len(m.group()), text)


def _split_rows(body):
    """Строки align и подобных окружений → [(смещение, текст)]. \\\\ внутри cases, матриц и {} не разделяет."""
    masked = re.sub(r"\\begin\{(" + INNER_ENVS + r")\}.*?\\end\{\1\}", lambda m: " " * len(m.group()), body, flags=re.S)
    rows, start, depth, i = [], 0, 0, 0
    while i < len(masked):
        pair = masked[i:i + 2]
        if pair in ("\\{", "\\}"):
            i += 2
        elif pair == "\\\\" and depth == 0:
            rows.append((start, body[start:i]))
            start = i = i + 2
        else:
            depth += {"{": 1, "}": -1}.get(masked[i], 0)
            i += 1
    return rows + [(start, body[start:])]


def _numbered_rows(doc):
    """Все нумерованные формулы → [(смещение, номер, метки)]. Номер сквозной или по разделам
    (\\numberwithin{equation}{section}), строка с \\nonumber или \\notag номера не получает."""
    text = _blank_comments(doc.text)
    by_section = re.search(r"\\numberwithin\{equation\}\{section\}", text)
    events = sorted([(m.start(), "sec", m) for m in re.finditer(r"\\section\s*\{", text)]
                    + [(m.start(), "app", m) for m in re.finditer(r"\\appendix\b", text)]
                    + [(m.start(), "env", m) for m in re.finditer(r"\\begin\{(" + NUMBERED_ENVS + r")\}", text)],
                    key=lambda e: e[0])
    out, sec, n, appendix = [], 0, 0, False
    for off, kind, m in events:
        if kind == "app":
            appendix, sec = True, 0
        elif kind == "sec":
            sec += 1
            n = 0 if by_section else n
        else:
            name = m.group(1)
            end = text.find(f"\\end{{{name}}}", m.end())
            body = text[m.end():end if end >= 0 else len(text)]
            for row_off, row in ([(0, body)] if name in ("equation", "multline") else _split_rows(body)):
                if not row.strip() or re.search(r"\\(nonumber|notag)\b", row):
                    continue
                n += 1
                prefix = f"{chr(64 + sec) if appendix else sec}." if by_section else ""
                out.append((m.end() + row_off, prefix + str(n), re.findall(r"\\label\{([^}]+)\}", row)))
    return out


def _prose_without_math(doc):
    text = re.sub(r"(?<!\\)%.*", "", doc.text)
    text = re.sub(r"\\begin\{(equation|align|eqnarray|gather|multline)\*?\}.*?\\end\{\1\*?\}", " ", text, flags=re.S)
    text = re.sub(r"\\\w*(?:ref|label|cite\w*)\*?\{[^}]*\}", " ", text)  # метки вроде FarhiEq12 это не «Eq 12»
    return re.sub(r"\$[^$]*\$", " ", " ".join(text.split()))


def _cited_by_number(prose, number):
    """Ссылка номером, вписанным вручную: «Eq. 3», «equation (3)» или «(1.2)». Голое «(3)» не считается:
    так же выглядят перечисления."""
    if not number:
        return False
    word = r"(?<![\wА-Яа-я])(?:Eq|Eqn|Equation|equation|formula|формул[аеуы])s?\.?~?\s*\(?" + re.escape(number) + r"\b"
    pat = word if "." not in number else r"\(" + re.escape(number) + r"\)|" + word
    return re.search(pat, prose) is not None


CITE_CMDS = ("cite", "citep", "citet", "citealp")
UNSORTED_BST = {"unsrt", "unsrtnat", "ieeetr", "ieeetran", "ugost2003", "ugost2008", "splncs04", "sn-mathphys-num"}


def first_cite_order(doc):
    seen = []
    for _, arg in sorted(o for name in CITE_CMDS for o in doc.commands(name)):
        for key in arg.split(","):
            if key.strip() and key.strip() not in seen:
                seen.append(key.strip())
    return seen


def _check_cite_order(doc, add):
    """Список литературы нумеруется в порядке первого цитирования: по .bbl, иначе по стилю."""
    cited = first_cite_order(doc)
    bbl = Path(doc.root).with_suffix(".bbl")
    if bbl.is_file():
        listed = re.findall(r"\\(?:bibitem(?:\[[^\]]*\])?|entry)\{([^}]+)\}", bbl.read_text(errors="replace"))
        listed = [k for k in listed if k in cited]
        if listed != [k for k in cited if k in listed]:
            add("FMT_CITE_ORDER", ERROR, None, "Список литературы не в порядке цитирования",
                "Первая в тексте ссылка должна быть [1]: стиль unsrt или sorting=none")
        return
    styles = [s.strip().lower() for _, s in doc.commands("bibliographystyle")]
    if styles:
        if styles[0] not in UNSORTED_BST:
            add("FMT_CITE_ORDER", ERROR, None, f"Стиль {styles[0]} сортирует список не в порядке цитирования",
                "Возьмите unsrt, unsrtnat или ugost2008")
    elif re.search(r"\\usepackage\[[^\]]*sorting\s*=\s*none[^\]]*\]\{biblatex\}", doc.text) is None:
        add("FMT_CITE_ORDER", INFO, None, "Порядок списка литературы не проверен: нет .bbl и стиля unsrt",
            "Для biblatex укажите sorting=none")


def check_references(doc, report, profile, entries, people=None, today=None):
    """Число, свежесть источников и доля самоцитирования (авторы статьи + их варианты имён из реестра)."""
    cfg = profile.get("references", {})
    cited = set(first_cite_order(doc))
    used = [e for e in entries if e["key"] in cited] or entries
    where = doc.rel(doc.root)
    if cfg.get("min_count") and len(used) < cfg["min_count"]:
        report.add("BIB_TOO_FEW", WARNING, f"Источников {len(used)}, нужно не меньше {cfg['min_count']}", where)

    years = [int(m.group()) for e in used for m in [re.search(r"\d{4}", e["fields"].get("year", ""))] if m]
    recent = cfg.get("recent")
    if recent and years:
        since = (today or date.today()).year - recent["years"]
        share = sum(y >= since for y in years) / len(years)
        if share < recent["min_share"]:
            report.add("BIB_NOT_RECENT", WARNING,
                       f"Источников не старше {recent['years']} лет {share:.0%}, нужно от {recent['min_share']:.0%}",
                       where, hint="Добавьте свежие работы по теме")

    limit = cfg.get("self_citation_max")
    if limit is not None and used:
        own = _author_surnames(doc, people)
        mine = [e["key"] for e in used if own & _bib_surnames(e["fields"].get("author", ""))]
        share = len(mine) / len(used)
        if share > limit:
            report.add("BIB_SELF_CITATION", WARNING, f"Самоцитирование {share:.0%} при пределе {limit:.0%}", where,
                       hint="Свои работы: " + ", ".join(mine))


def _author_surnames(doc, people):
    from ..registry import _norm, paper_authors
    names = {_norm(n) for _, n in paper_authors(doc)}
    for p in people or []:
        variants = {_norm(p.get(k, "")) for k in ("name_en", "name_ru") if p.get(k)}
        if any(set(v.split()) & set(n.split()) for v in variants for n in names):
            names |= variants
    return {w for n in names for w in n.split() if len(w) > 2}


def _bib_surnames(author_field):
    from ..registry import _norm
    out = set()
    for a in re.split(r"\s+and\s+", author_field):
        a = re.sub(r"[{}\\]", "", a)
        surname = a.split(",")[0] if "," in a else (a.split() or [""])[-1]
        out.add(_norm(surname))
    return out


def _check_graphic(doc, path, cfg, add):
    if "\\" in path:  # путь собирается макросом (\iftoggle, \figdir...) — статически не вычислить
        add("FMT_FIGURE_FILE", INFO, f"Путь к рисунку задан макросом, файл не проверен: {path[:80]}")
        return
    base = Path(doc.root).parent
    dirs = [base]
    for _, arg in doc.commands("graphicspath"):
        dirs += [base / d for d in re.findall(r"\{([^{}]*)\}", arg)]
    exts = cfg.get("allowed_ext", ["pdf", "png"])
    candidates = [d / p for d in dirs for p in [path] + [f"{path}.{e}" for e in exts]]
    real = next((c for c in candidates if c.is_file()), None)
    if real is None:
        add("FMT_FIGURE_FILE", ERROR, f"Файл рисунка не найден: {path}")
        return
    ext = real.suffix.lstrip(".").lower()
    if cfg.get("allowed_ext") and ext not in cfg["allowed_ext"]:
        add("FMT_FIGURE_FORMAT", ERROR, f"Формат .{ext} не разрешён: {', '.join(cfg['allowed_ext'])}")
    if cfg.get("dir") and cfg["dir"].strip("/") not in real.resolve().parent.parts:
        add("FMT_FIGURE_DIR", WARNING, f"Рисунок {path} лежит не в папке {cfg['dir']}/")
