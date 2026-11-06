"""Строки с номером, которые gitsci не отметил: какая причина сработала."""

import re

import holdout
import run as arxiv
from gitsci.findings import Report
from gitsci.latex import fmt, texdoc

for pid in ("1411.4028", "1609.02907"):
    paper = holdout.CORPUS / pid
    doc = texdoc.load(arxiv.main_tex(paper))
    r = Report()
    fmt.check(doc, r, arxiv.PROFILE, arxiv.bib_keys(paper, arxiv.main_tex(paper)))
    flagged = {re.search(r"\(([\w.]+)\)", f.message).group(1) for f in r.findings if f.rule == "FMT_EQ_UNREFERENCED"}
    wrappers = re.findall(r"\\(?:re)?newcommand\*?\{?\\(\w+)\}?\[\d\](?:\[[^\]]*\])?\{[^\n]*?\\\w*ref\*?\{#1\}", doc.text)
    refs = {a.strip() for n in ("ref", "eqref", "autoref", "cref", "Cref", *wrappers) for _, x in doc.commands(n) for a in x.split(",")}
    prose = fmt._prose_without_math(doc)
    print(pid, "обёртки", wrappers, "отмечено", len(flagged))
    for off, num, labs in fmt._numbered_rows(doc):
        if num in flagged:
            continue
        by_ref = [x for x in labs if x in refs]
        by_num = fmt._cited_by_number(prose, num)
        print("  ", num, labs, "ссылка" if by_ref else "", "номером" if by_num else "")
        if by_num:
            m = re.search(r"(?<![\wА-Яа-я])(?:Eq|Eqn|Equation|equation|formula)s?\.?~?\s*\(?" + re.escape(num) + r"\b", prose)
            print("      ", prose[max(0, m.start() - 50):m.end() + 25] if m else "")
