import re
import shutil
import zipfile
from importlib import resources
from pathlib import Path

import yaml

from gitsci import publish, zipcheck
from gitsci.findings import Report

ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / "demo" / "paper-spsa"


def _zip_dir(src, dst, root="project"):
    with zipfile.ZipFile(dst, "w") as z:
        for f in Path(src).rglob("*"):
            if f.is_file() and "__pycache__" not in f.parts:
                z.write(f, f"{root}/{f.relative_to(src).as_posix()}")
    return dst


def test_every_rule_is_in_ontology():
    onto = yaml.safe_load(resources.files("gitsci.data").joinpath("ontology.yml").read_text(encoding="utf-8"))
    code = "".join(p.read_text(encoding="utf-8") for p in (ROOT / "gitsci" / "gitsci").rglob("*.py"))
    used = set(re.findall(r'"((?:STYLE|EQ|TEX|FMT|BIB|REG|AUTH|PLAN|FIG|EXP|ZIP|PUB)_[A-Z_]+)"', code))
    assert used - set(onto["rules"]) == set()


def test_demo_zip_accepted(tmp_path):
    z = _zip_dir(DEMO, tmp_path / "ok.zip")
    report, accepted, _ = zipcheck.check(z, offline=True)
    assert accepted, report.to_text()


def test_overleaf_flat_zip_rejected(tmp_path):
    z = tmp_path / "overleaf.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("main.tex", "\\documentclass{article}\\begin{document}x\\end{document}")
        zf.writestr("refs.bib", "")
        zf.writestr("__MACOSX/._main.tex", "")
    report, accepted, _ = zipcheck.check(z, offline=True)
    rules = {f.rule for f in report.findings}
    assert not accepted and {"ZIP_FLAT_OVERLEAF", "ZIP_MISSING", "ZIP_FORBIDDEN_FILE"} <= rules


def test_zip_slip_rejected(tmp_path):
    z = tmp_path / "evil.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("../../evil.txt", "x")
    report, accepted, _ = zipcheck.check(z, offline=True)
    assert not accepted and report.findings[0].rule == "ZIP_UNSAFE_PATH"


def test_publish_excludes_internal_and_finds_secrets(tmp_path):
    src = tmp_path / "proj"
    shutil.copytree(DEMO, src, ignore=shutil.ignore_patterns("__pycache__"))
    report = Report()
    files = publish.export(src, tmp_path / "out", publish.load(src / "publish.yml"), report)
    assert "plan.yml" not in files and "AGENTS.md" not in files
    assert not any(f.startswith("paper/ru/") for f in files)
    assert "src/model.py" in files and not report.findings
    (src / "src" / "leak.py").write_text('TOKEN = "glpat-abcdefghijklmnopqrstuvwx"\n', encoding="utf-8")
    report = Report()
    publish.export(src, tmp_path / "out2", publish.load(src / "publish.yml"), report)
    assert [f.rule for f in report.findings] == ["PUB_SECRET"]
