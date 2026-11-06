import json
from datetime import date

from gitsci import bib, figures, plan, registry
from gitsci.findings import Report
from gitsci.latex import fmt, style, texdoc
from gitsci.profile import load as load_profile

STYLE = load_profile("lab")["style"]


def rules(report):
    return [f.rule for f in report.findings]


def tex(tmp_path, body, name="main.tex"):
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return texdoc.load(path)


def test_semicolon_only_in_prose(tmp_path):
    doc = tex(tmp_path, "Текст; ещё текст.\n\\begin{equation} f(x;\\theta) = 1 \\end{equation}\n")
    r = Report()
    style.check(doc, r, STYLE)
    assert rules(r).count("STYLE_SEMICOLON") == 1
    assert r.findings[0].line == 1


def test_dashes(tmp_path):
    doc = tex(tmp_path, "Метод --- лучший.\nМомент -- в отличие от схемы -- сглаживает.\nДиапазон 1--5 допустим.\n")
    r = Report()
    style.check(doc, r, STYLE)
    assert "STYLE_TRIPLE_DASH" not in rules(r)  # одиночное тире разрешено профилем lab
    assert rules(r).count("STYLE_PAIRED_DASH") == 1
    strict = Report()
    style.check(doc, strict, {**STYLE, "triple_dash": "error"})
    assert "STYLE_TRIPLE_DASH" in rules(strict)


def test_fragmented_equation(tmp_path):
    doc = tex(tmp_path, "\\begin{equation}\nf(x)\n=\n2x^2\n+\n3\n\\end{equation}\n")
    r = Report()
    style.check(doc, r, STYLE)
    assert "EQ_FRAGMENTED" in rules(r)


def test_normal_equation_ok(tmp_path):
    doc = tex(tmp_path, "\\begin{align}\na &= b + c \\\\\nd &= e + f\n\\end{align}\n")
    r = Report()
    style.check(doc, r, STYLE)
    assert "EQ_FRAGMENTED" not in rules(r)


def test_contrast_and_water_ru(tmp_path):
    doc = tex(tmp_path, "Стоит отметить, что метод не просто быстрый, а устойчивый к шуму и данным.\n")
    r = Report()
    style.check(doc, r, STYLE)
    assert "STYLE_WATER" in rules(r) and "STYLE_CONTRAST" in rules(r)


def test_contrast_en(tmp_path):
    doc = tex(tmp_path, "The method is not only fast but also robust to noise in measurements.\n")
    r = Report()
    style.check(doc, r, STYLE)
    assert "STYLE_CONTRAST" in rules(r)


def test_commands_are_not_prose(tmp_path):
    doc = tex(tmp_path, "See \\cite{a;b} and \\ref{fig:x}. \\url{http://a.b/c;d}\n")
    r = Report()
    style.check(doc, r, STYLE)
    assert "STYLE_SEMICOLON" not in rules(r)


def test_input_resolution_and_location(tmp_path):
    (tmp_path / "sec").mkdir()
    (tmp_path / "sec" / "a.tex").write_text("Первая строка.\nВторая; строка.\n", encoding="utf-8")
    doc = tex(tmp_path, "\\input{sec/a}\n")
    r = Report()
    style.check(doc, r, STYLE)
    f = next(x for x in r.findings if x.rule == "STYLE_SEMICOLON")
    assert f.file.endswith("sec/a.tex") and f.line == 2


def test_format_sections_and_abstract(tmp_path):
    doc = tex(tmp_path, "\\documentclass{article}\\usepackage{amsmath,graphicx,hyperref}\\title{T}\n"
                        "\\begin{abstract}" + "word " * 300 + "\\end{abstract}\n\\section{Introduction}\n")
    r = Report()
    fmt.check(doc, r, load_profile("lab"))
    assert "FMT_ABSTRACT_LENGTH" in rules(r)
    assert "FMT_SECTION_MISSING" in rules(r)


def test_bib_parse_and_doi_mismatch(tmp_path):
    p = tmp_path / "r.bib"
    p.write_text("@article{a, title={Array programming with {NumPy}}, doi={10.1038/s41586-020-2649-2},"
                 " author={Harris, C.}, journal={Nature}, year={2020}}\n"
                 "@article{b, title={Something else entirely}, doi={10.1038/s41586-020-2649-2},"
                 " author={X, Y}, journal={J}, year={2020}}\n", encoding="utf-8")
    cache = tmp_path / "c.json"
    cache.write_text(json.dumps({"10.1038/s41586-020-2649-2": {
        "title": "Array programming with NumPy", "year": 2020, "first_author": "Harris", "container": "Nature"}}))
    r = Report()
    bib.check(p, r, {}, crossref=bib.Crossref(offline=True, cache_path=cache))
    assert rules(r) == ["BIB_DOI_TITLE_MISMATCH"]
    assert r.findings[0].message.startswith("b:")


def test_orcid_checksum():
    assert registry.orcid_valid("0000-0002-1825-0097")
    assert not registry.orcid_valid("0000-0002-1825-0098")


def test_registry_stale(tmp_path):
    (tmp_path / "people").mkdir()
    (tmp_path / "people" / "x.yml").write_text(
        "id: x\nname_ru: Иванов Иван\nname_en: Ivan Ivanov\nemail: a@b.cd\n"
        "affiliations: [{name_ru: У, name_en: U}]\nupdated: 2026-01-01\norcid: 0000-0002-1825-0098\n",
        encoding="utf-8")
    r = Report()
    registry.check(tmp_path, r, today=date(2026, 10, 26))
    assert "REG_STALE" in rules(r) and "REG_ORCID_CHECKSUM" in rules(r)


def test_author_spelling(tmp_path):
    people = [{"name_en": "Maria Petrova", "name_ru": "Петрова Мария Алексеевна", "_file": "p.yml"}]
    doc = tex(tmp_path, "\\author[1]{Mariya Petrova}\nText in English here.\n")
    r = Report()
    registry.check_paper_authors(doc, people, r, today=date(2026, 10, 26))
    assert rules(r) == ["AUTH_NAME_SPELLING"]


def test_plan_en_before_approval(tmp_path):
    (tmp_path / "en.tex").write_text("\\section{R}\nThis is english text written too early indeed.\n",
                                     encoding="utf-8")
    (tmp_path / "ru.tex").write_text("Текст.", encoding="utf-8")
    (tmp_path / "plan.yml").write_text(
        "supervisor: boss\nsections:\n- {id: r, owner: a, due_ru: 2026-11-01, due_en: 2026-11-10,"
        " ru: ru.tex, en: en.tex, status: draft_ru}\n- {id: s, owner: a, due_ru: 2026-11-01, due_en: 2026-11-10,"
        " ru: ru.tex, en: en.tex, status: approved_ru, approved_by: student}\n", encoding="utf-8")
    r = Report()
    plan.check(tmp_path / "plan.yml", r, today=date(2026, 10, 26))
    assert "PLAN_EN_BEFORE_APPROVAL" in rules(r)
    assert "PLAN_APPROVAL" in rules(r)


def test_cvd_red_green():
    d, _ = figures.min_distance(["#d62728", "#2ca02c"], figures.CVD["дейтеранопия"])
    ok, _ = figures.min_distance(["#0072B2", "#E69F00"], figures.CVD["дейтеранопия"])
    assert d < 12 < ok


def test_abstract_keywords_declarations(tmp_path):
    prof = {"abstract": {"no_citations": True, "no_math": True}, "keywords": {"comma_separated": True},
            "declarations": [["Funding", "Финансирование"], ["Use of generative AI"]]}
    doc = tex(tmp_path, "\\begin{abstract}As in \\cite{a}, $x=1$.\\end{abstract}\n\\keywords{one; two.}\n"
                        "\\section*{Финансирование}\nНе применимо.\n")
    r = Report()
    fmt.check(doc, r, prof)
    got = rules(r)
    assert {"FMT_ABSTRACT_CITE", "FMT_ABSTRACT_MATH", "FMT_KEYWORDS_FORMAT"} <= set(got)
    assert got.count("FMT_DECLARATION_MISSING") == 1  # есть «Финансирование», нет заявления об ИИ


def test_abstract_min_words_and_keywords_macro(tmp_path):
    prof = {"abstract": {"min_words": 150}, "keywords": {"command": "keywordsru", "min": 3, "max": 7}}
    doc = tex(tmp_path, "\\begin{abstract}Коротко.\\end{abstract}\n\\keywordsru{один, два, три}\n")
    r = Report()
    fmt.check(doc, r, prof)
    assert "FMT_ABSTRACT_LENGTH" in rules(r)  # короткая аннотация отмечена
    assert "FMT_KEYWORDS" not in rules(r)     # макрос шаблона найден


def test_equation_numbering_and_pages(tmp_path):
    doc = tex(tmp_path, "\\begin{equation}a=b\\label{eq:a}\\end{equation}\n"
                        "\\begin{equation}c=d\\label{eq:c}\\end{equation}\nСм. \\eqref{eq:a}.\n")
    (tmp_path / "main.log").write_text("Output written on main.pdf (23 pages, 1000 bytes).")
    r = Report()
    fmt.check(doc, r, {"equations": {"number_only_referenced": True}, "pages": {"max": 20}})
    assert rules(r).count("FMT_EQ_UNREFERENCED") == 1
    assert "FMT_PAGES" in rules(r)


def test_equation_referenced_by_hand_number(tmp_path):
    doc = tex(tmp_path, "\\numberwithin{equation}{section}\n\\section{A}\n"
                        "\\begin{equation}a=b\\end{equation}\n\\begin{equation}c=d\\end{equation}\n"
                        "\\begin{equation}e=f\\nonumber\\end{equation}\nКак видно из (1.2), всё сходится.\n")
    r = Report()
    fmt.check(doc, r, {"equations": {"number_only_referenced": True}})
    assert rules(r).count("FMT_EQ_UNREFERENCED") == 1  # (1.1) без ссылки, (1.2) упомянута, третья без номера


def test_multiline_equations(tmp_path):
    doc = tex(tmp_path, "\\begin{align}\na &= b \\label{eq:a} \\\\\nc &= d \\nonumber \\\\\n"
                        "e &= \\begin{cases} 1 \\\\ 2 \\end{cases}\n\\end{align}\n"
                        "\\begin{multline}\nf = g\n\\end{multline}\n"
                        "%\\begin{equation} h = i \\end{equation}\nСм. \\eqref{eq:a}.\n")
    r = Report()
    fmt.check(doc, r, {"equations": {"number_only_referenced": True}})
    # без ссылки: третья строка align (вторая без номера, cases не делит строку) и multline, комментарий не считается
    assert rules(r).count("FMT_EQ_UNREFERENCED") == 2


def test_label_with_number_is_not_hand_reference(tmp_path):
    doc = tex(tmp_path, "\\begin{equation}a=b\\label{FarhiEq2}\\end{equation}\n"
                        "\\begin{equation}c=d\\label{FarhiEq7}\\end{equation}\nСм. \\eqref{FarhiEq2}.\n")
    r = Report()
    fmt.check(doc, r, {"equations": {"number_only_referenced": True}})
    # формула 2 без ссылки: \eqref{FarhiEq2} относится к формуле 1, а не к номеру 2
    assert rules(r).count("FMT_EQ_UNREFERENCED") == 1


def test_subfigures_and_wrapper_macros(tmp_path):
    doc = tex(tmp_path, "\\newcommand{\\figref}[1]{Fig.~\\ref{#1}}\n"
                        "\\begin{figure}\\caption{A}\\label{fig:a-1}\\caption{B}\\label{fig:a}\\end{figure}\n"
                        "\\begin{figure}\\caption{C}\\label{fig:b}\\end{figure}\nСм. \\ref{fig:a} и \\figref{fig:b}.\n")
    r = Report()
    fmt.check(doc, r, {})
    assert "FMT_FIGURE_UNREFERENCED" not in rules(r)
    assert "FMT_REF_UNDEFINED" not in rules(r)


def test_cite_order(tmp_path):
    body = "\\cite{b} затем \\cite{a}.\n\\bibliographystyle{plain}\n"
    r = Report()
    fmt.check(tex(tmp_path, body), r, {"references": {"order": "citation"}})
    assert "FMT_CITE_ORDER" in rules(r)
    (tmp_path / "main.bbl").write_text("\\bibitem{b} B.\n\\bibitem{a} A.\n")
    ok = Report()
    fmt.check(tex(tmp_path, body), ok, {"references": {"order": "citation"}})
    assert "FMT_CITE_ORDER" not in rules(ok)


def test_references_count_recency_self_citation(tmp_path):
    doc = tex(tmp_path, "\\author{Kirill Chernikov}\n\\cite{a,b,c}\n")
    entries = [{"key": "a", "fields": {"author": "Черников, К.", "year": "2010"}},
               {"key": "b", "fields": {"author": "Smith, J. and Doe, A.", "year": "2011"}},
               {"key": "c", "fields": {"author": "Chernikov, K.", "year": "2025"}}]
    people = [{"name_en": "Kirill Chernikov", "name_ru": "Черников Кирилл"}]
    prof = {"references": {"min_count": 15, "recent": {"years": 5, "min_share": 0.5}, "self_citation_max": 0.2}}
    r = Report()
    fmt.check_references(doc, r, prof, entries, people, today=date(2026, 10, 30))
    assert {"BIB_TOO_FEW", "BIB_NOT_RECENT", "BIB_SELF_CITATION"} <= set(rules(r))
    assert "a" in r.findings[-1].hint  # русское написание найдено через реестр
