"""Загрузка LaTeX-документа с \\input/\\include и разметка «что здесь проза, а что формулы/команды».

Всё, что не является прозой, в `prose` заменяется пробелами с сохранением длины и переводов строк,
поэтому смещение в `prose` однозначно переводится в (файл, строка) исходника.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

MATH_ENVS = ("equation", "align", "gather", "multline", "eqnarray", "math", "displaymath", "flalign", "alignat")
VERBATIM_ENVS = ("verbatim", "lstlisting", "minted", "comment")
# Аргументы этих команд — не проза (ключи, пути, имена пакетов, URL).
NONPROSE_COMMANDS = {
    "label", "ref", "eqref", "autoref", "cref", "Cref", "pageref", "cite", "citep", "citet", "citealp",
    "citeauthor", "citeyear", "nocite", "usepackage", "documentclass", "includegraphics", "bibliography",
    "bibliographystyle", "input", "include", "url", "begin", "end", "newcommand", "renewcommand",
    "def", "setlength", "setcounter", "hypersetup", "graphicspath", "affil", "email", "orcid", "jyear",
    "theoremstyle", "newtheorem", "raggedbottom", "fnm", "sur", "author", "address", "pacs", "keywords",
}
_INPUT_RE = re.compile(r"\\(input|include)\s*\{([^}]+)\}")


@dataclass
class Line:
    file: str
    no: int
    raw: str
    code: str  # без комментариев


@dataclass
class TexDoc:
    root: Path
    lines: list = field(default_factory=list)
    text: str = ""        # код без комментариев, строки через \n
    prose: str = ""       # только проза
    starts: list = field(default_factory=list)
    math_blocks: list = field(default_factory=list)  # (env, start_offset, end_offset)

    # --- координаты --------------------------------------------------------
    def locate(self, offset):
        """Смещение в text/prose → (файл, номер строки)."""
        lo, hi = 0, len(self.starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self.starts[mid] <= offset:
                lo = mid
            else:
                hi = mid - 1
        ln = self.lines[lo]
        return ln.file, ln.no

    def rel(self, file):
        try:
            return str(Path(file).resolve().relative_to(Path.cwd().resolve())).replace("\\", "/")
        except ValueError:
            return str(file).replace("\\", "/")

    # --- структура ---------------------------------------------------------
    def commands(self, name):
        """Все вхождения \\name[..]{arg} → (offset, arg). Аргумент со вложенными скобками."""
        out = []
        for m in re.finditer(r"\\" + re.escape(name) + r"\*?\s*(\[[^\]]*\])?\s*\{", self.text):
            arg, _ = read_group(self.text, m.end() - 1)
            out.append((m.start(), arg))
        return out

    def environments(self, name):
        """Содержимое \\begin{name}...\\end{name} → (start_offset, body)."""
        pat = re.compile(r"\\begin\{" + re.escape(name) + r"\}(.*?)\\end\{" + re.escape(name) + r"\}", re.S)
        return [(m.start(), m.group(1)) for m in pat.finditer(self.text)]

    def language(self):
        letters = re.findall(r"[A-Za-zА-Яа-яЁё]", self.prose)
        if not letters:
            return "en"
        cyr = sum(1 for ch in letters if "А" <= ch <= "я" or ch in "Ёё")
        return "ru" if cyr / len(letters) > 0.3 else "en"


def strip_comment(line):
    """Убирает % до конца строки, кроме экранированного \\%."""
    i = 0
    while i < len(line):
        if line[i] == "\\":
            i += 2
            continue
        if line[i] == "%":
            return line[:i]
        i += 1
    return line


def read_group(text, open_pos):
    """text[open_pos] == '{' → (содержимое, позиция после '}')."""
    depth, i = 0, open_pos
    while i < len(text):
        ch = text[i]
        if ch == "\\":
            i += 2
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[open_pos + 1:i], i + 1
        i += 1
    return text[open_pos + 1:], len(text)


def _collect(path, out, seen):
    path = Path(path)
    if path.suffix != ".tex" and not path.exists():
        path = path.with_suffix(".tex")
    key = path.resolve()
    if key in seen or not path.exists():
        return
    seen.add(key)
    for no, raw in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        code = strip_comment(raw)
        m = _INPUT_RE.search(code)
        if m:
            out.append(Line(str(path), no, raw, code[:m.start()] + " " * (len(code) - m.start())))
            _collect(path.parent / m.group(2).strip(), out, seen)
        else:
            out.append(Line(str(path), no, raw, code))


def load(root):
    doc = TexDoc(Path(root))
    _collect(root, doc.lines, set())
    pos = 0
    for ln in doc.lines:
        doc.starts.append(pos)
        pos += len(ln.code) + 1
    doc.text = "\n".join(ln.code for ln in doc.lines)
    doc.prose = _mask(doc)
    return doc


def _blank(chars, a, b):
    for i in range(a, b):
        if chars[i] != "\n":
            chars[i] = " "


def _mask(doc):
    text = doc.text
    chars = list(text)
    envs = "|".join(MATH_ENVS + VERBATIM_ENVS)
    for m in re.finditer(r"\\begin\{((?:" + envs + r")\*?)\}(.*?)\\end\{\1\}", text, re.S):
        env = m.group(1).rstrip("*")
        if env in MATH_ENVS:
            doc.math_blocks.append((m.group(1), m.start(2), m.end(2)))
        _blank(chars, m.start(), m.end())
    for pat in (r"\$\$.*?\$\$", r"(?<!\\)\$.*?(?<!\\)\$", r"\\\[.*?\\\]", r"\\\(.*?\\\)"):
        for m in re.finditer(pat, text, re.S):
            _blank(chars, m.start(), m.end())
    for m in re.finditer(r"\\([A-Za-z@]+)\*?", text):
        _blank(chars, m.start(), m.end())
        if m.group(1) in NONPROSE_COMMANDS:
            i = m.end()
            while i < len(text) and text[i] in " \t[{":
                if text[i] == "[":
                    j = text.find("]", i)
                    if j < 0:
                        break
                    _blank(chars, i, j + 1)
                    i = j + 1
                elif text[i] == "{":
                    _, j = read_group(text, i)
                    _blank(chars, i, j)
                    i = j
                    if m.group(1) not in ("newcommand", "renewcommand", "href", "setlength", "setcounter"):
                        break
                else:
                    i += 1
    for m in re.finditer(r"\\[^A-Za-z]|[{}~]", text):  # \% \\ \, скобки и неразрывные пробелы
        _blank(chars, m.start(), m.end())
    return "".join(chars)
