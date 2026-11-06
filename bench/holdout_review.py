"""Сводка отложенной выборки и подготовка замечаний к ручной разметке (bench/holdout_precision.csv)."""

import csv
import json
import re
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
data = json.loads((HERE / "raw/holdout.json").read_text(encoding="utf-8"))
rows = [r for r in data["rows"] if r["applicable"]]
print("применимо", len(rows), "неприменимо", len(data["rows"]) - len(rows))
for op in sorted({r["op"] for r in rows}):
    rs = [r for r in rows if r["op"] == op]
    ok = [r for r in rs if r["chklref"] is not None]
    print(f"{op}: {len(rs)} gitsci {sum(r['gitsci'] for r in rs)} latex {sum(r['latex'] for r in rs)} "
          f"textidote {sum(r['textidote'] for r in rs)} chklref {sum(bool(r['chklref']) for r in ok)}/{len(ok)}")
    miss = [r["paper"] for r in rs if not r["gitsci"]]
    if miss:
        print("   gitsci пропустил:", miss)

out = []
for paper, info in data["base"].items():
    root = HERE / "corpus_holdout" / paper
    tex = "\n".join(re.sub(r"(?<!\\)%.*", "", p.read_text(encoding="utf-8", errors="replace")) for p in root.rglob("*.tex"))
    for rule, file, line, msg in info["gitsci"]:
        path = HERE / file if (HERE / file).exists() else root / file
        src = path.read_text(encoding="utf-8", errors="replace").split("\n") if path.exists() else []
        label = (re.search(r"рисунок (\S+) нет", msg) or [None, ""])[1]
        uses = len(re.findall(r"(?<!\\label)\{[^{}]*\b" + re.escape(label) + r"\b[^{}]*\}", tex)) if label else ""
        ctx = " ".join(" ".join(src[max(0, line - 2):line + 1]).split())[:200]
        out.append({"paper": paper, "rule": rule, "file": file, "line": line, "message": msg, "uses": uses, "context": ctx,
                    "verdict": "", "reason": ""})
with open(HERE / "holdout_precision.csv", "w", newline="", encoding="utf-8-sig") as fh:
    w = csv.DictWriter(fh, fieldnames=list(out[0]))
    w.writeheader()
    w.writerows(out)
print(Counter(o["rule"] for o in out))
for o in out:
    if o["rule"] != "FMT_EQ_UNREFERENCED":
        print(o["paper"], o["rule"], o["line"], o["uses"], o["context"][:110])
print("textidote:", {p: i["textidote_fig"] for p, i in data["base"].items() if i["textidote_fig"]})
print("chklref:", {p: Counter("STAR" if "STAR" in k else "label" if "remove label" in k else "other" for k in i["chklref"])
                   for p, i in data["base"].items() if i["chklref"] is not None})
