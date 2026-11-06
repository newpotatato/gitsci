"""Ручные ссылки на формулы по номеру: «(1.2)», «Eq. 3», «equation (4)».

Вычисляет номер каждой нумерованной формулы (equation без звёздочки; с \\numberwithin по разделам или сквозной)
и ищет этот номер в тексте вне формул. Нужен для честной разметки FMT_EQ_UNREFERENCED: правило видит
только \\ref и \\eqref, а у части авторов номера вписаны руками.
"""

import re
import sys
from pathlib import Path

import run as arxiv
from gitsci.latex import texdoc


def numbered(doc):
    """[(offset, номер)] для equation; учитывает \\numberwithin{equation}{section} и \\section*."""
    text = doc.text
    by_section = re.search(r"\\numberwithin\{equation\}\{section\}|\\renewcommand\{?\\theequation\}?\{\\(?:the|arabic\{)section", text)
    events = [(m.start(), "sec") for m in re.finditer(r"\\section\s*\{", text)]
    events += [(m.start(), "app") for m in re.finditer(r"\\appendix\b", text)]
    events += [(m.start(), "eq") for m in re.finditer(r"\\begin\{equation\}", text)]
    out, sec, n, letters = [], 0, 0, False
    for off, kind in sorted(events):
        if kind == "app":
            letters, sec = True, 0
        elif kind == "sec":
            sec += 1
            if by_section:
                n = 0
        else:
            body = text[off:text.find("\\end{equation}", off)]
            if re.search(r"\\(nonumber|notag)\b", body):
                continue
            n += 1
            prefix = (chr(64 + sec) if letters else str(sec)) + "." if by_section else ""
            out.append((off, f"{prefix}{n}"))
    return out


def referenced_by_number(doc, number):
    """Номер упомянут в тексте вне формул и комментариев. Голые «(3)» не считаются: это часто перечисления,
    O(1) или log(4). Без слова «Eq./equation» засчитываются только составные номера вида «(1.2)»."""
    text = re.sub(r"(?<!\\)%.*", "", doc.text)
    prose = re.sub(r"\\begin\{(equation|align|eqnarray)\*?\}.*?\\end\{\1\*?\}", " ", text, flags=re.S)
    prose = re.sub(r"\$[^$]*\$", " ", " ".join(prose.split()))
    word = r"(?:Eq|Eqn|Equation|equation|formula)s?\.?~?\s*\(?" + re.escape(number) + r"\b"
    pat = word if "." not in number else r"\(" + re.escape(number) + r"\)|" + word
    return re.search(pat, prose) is not None


if __name__ == "__main__":
    for paper in sorted(arxiv.CORPUS.iterdir()):
        m = arxiv.main_tex(paper)
        if not m:
            continue
        doc = texdoc.load(m)
        nums = numbered(doc)
        hits = [(doc.locate(o)[1], num) for o, num in nums if referenced_by_number(doc, num)]
        print(paper.name, f"формул {len(nums)}, на номер ссылаются вручную: {len(hits)}", hits[:12], file=sys.stdout)
