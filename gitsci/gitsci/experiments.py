"""Snapshot for experiments: версия кода + результат каждого запуска.

    gitsci exp run -n lr-sweep -o "results/*.csv" -- python src/train.py --lr 0.1

Сохраняет в experiments/runs/<run_id>/:
  meta.json   — команда, коммит, ветка, «грязное» ли дерево, окружение, код возврата, метрики
  code.patch  — незакоммиченные изменения (то, чего нет в коммите, — например, правка формулы)
  untracked/  — новые файлы кода, ещё не добавленные в git
  stdout.log, stderr.log — полный вывод
  results/    — объявленные выходные файлы
Процесс получает GITSCI_RUN_ID и GITSCI_RUN_DIR; metrics.json в GITSCI_RUN_DIR попадает в meta.
"""

import csv
import glob
import json
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from .findings import ERROR, INFO, WARNING

RUNS = Path("experiments/runs")
INDEX = Path("experiments/index.csv")
CODE_EXT = {".py", ".ipynb", ".jl", ".m", ".r", ".R", ".cpp", ".c", ".h", ".yaml", ".yml", ".toml", ".json", ".sh"}


def _git(*args):
    r = subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.stdout if r.returncode == 0 else ""


def _tee(stream, sink, file):
    for line in iter(stream.readline, ""):
        sink.write(line)
        sink.flush()
        file.write(line)
    stream.close()


def run(name, command, outputs=(), note=""):
    started = datetime.now().astimezone()
    run_id = f"{started:%Y%m%d-%H%M%S}-{name}"
    run_dir = RUNS / run_id
    run_dir.mkdir(parents=True)

    commit = _git("rev-parse", "HEAD").strip()
    patch = _git("diff", "HEAD")
    untracked = [f for f in _git("ls-files", "--others", "--exclude-standard").splitlines()
                 if Path(f).suffix in CODE_EXT and not f.startswith(str(RUNS).replace("\\", "/"))]
    if patch:
        (run_dir / "code.patch").write_text(patch, encoding="utf-8")
    for f in untracked:
        dst = run_dir / "untracked" / f
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dst)
    freeze = subprocess.run([sys.executable, "-m", "pip", "freeze"], capture_output=True, text=True).stdout
    (run_dir / "requirements.lock.txt").write_text(freeze, encoding="utf-8")

    env = {**os.environ, "GITSCI_RUN_ID": run_id, "GITSCI_RUN_DIR": str(run_dir.resolve()),
           "PYTHONIOENCODING": "utf-8"}
    t0 = time.time()
    with open(run_dir / "stdout.log", "w", encoding="utf-8") as out, \
            open(run_dir / "stderr.log", "w", encoding="utf-8") as err:
        proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                encoding="utf-8", errors="replace", env=env)
        threads = [threading.Thread(target=_tee, args=(proc.stdout, sys.stdout, out)),
                   threading.Thread(target=_tee, args=(proc.stderr, sys.stderr, err))]
        for t in threads:
            t.start()
        code = proc.wait()
        for t in threads:
            t.join()

    saved = []
    for pattern in outputs:
        for f in glob.glob(pattern, recursive=True):
            dst = run_dir / "results" / f
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dst)
            saved.append(f.replace("\\", "/"))
    metrics_path = run_dir / "metrics.json"
    metrics = json.loads(metrics_path.read_text(encoding="utf-8")) if metrics_path.exists() else {}

    meta = {
        "run_id": run_id,
        "name": name,
        "note": note,
        "command": command,
        "started": started.isoformat(timespec="seconds"),
        "duration_s": round(time.time() - t0, 2),
        "exit_code": code,
        "git": {
            "commit": commit,
            "branch": _git("rev-parse", "--abbrev-ref", "HEAD").strip(),
            "dirty": bool(patch or untracked),
            "untracked": untracked,
        },
        "user": _git("config", "user.name").strip() or os.environ.get("USERNAME", ""),
        "env": {"python": platform.python_version(), "platform": platform.platform()},
        "outputs": saved,
        "metrics": metrics,
    }
    (run_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    new = not INDEX.exists()
    with open(INDEX, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["run_id", "commit", "dirty", "exit_code", "duration_s", "metrics"])
        w.writerow([run_id, commit[:10], meta["git"]["dirty"], code, meta["duration_s"],
                    json.dumps(metrics, ensure_ascii=False)])
    return run_id, code


def runs():
    out = []
    for meta in sorted(RUNS.glob("*/meta.json")):
        out.append(json.loads(meta.read_text(encoding="utf-8")))
    return out


def show_list():
    rows = runs()
    if not rows:
        return "Запусков нет. Пример: gitsci exp run -n test -- python src/train.py"
    lines = [f"{'run_id':<40} {'commit':<10} {'dirty':<6} {'exit':<5} metrics"]
    for m in rows:
        lines.append(f"{m['run_id']:<40} {m['git']['commit'][:10]:<10} {str(m['git']['dirty']):<6} "
                     f"{m['exit_code']:<5} {json.dumps(m.get('metrics', {}), ensure_ascii=False)}")
    return "\n".join(lines)


def diff(a, b):
    """Чем отличался код двух запусков: diff коммитов + их незакоммиченные патчи."""
    ma = json.loads((RUNS / a / "meta.json").read_text(encoding="utf-8"))
    mb = json.loads((RUNS / b / "meta.json").read_text(encoding="utf-8"))
    parts = [f"# {a}: {ma['git']['commit'][:10]}{' + патч' if ma['git']['dirty'] else ''}",
             f"# {b}: {mb['git']['commit'][:10]}{' + патч' if mb['git']['dirty'] else ''}"]
    if ma["git"]["commit"] != mb["git"]["commit"]:
        parts.append("## Разница коммитов\n" + _git("diff", ma["git"]["commit"], mb["git"]["commit"], "--", "."))
    for rid, m in ((a, ma), (b, mb)):
        p = RUNS / rid / "code.patch"
        if p.exists():
            parts.append(f"## Незакоммиченные правки в {rid}\n" + p.read_text(encoding="utf-8"))
    parts.append(f"## Метрики\n{a}: {ma.get('metrics')}\n{b}: {mb.get('metrics')}")
    return "\n".join(parts)


def check(report, figures_dir=None):
    ids = set()
    for run_dir in sorted(p for p in RUNS.glob("*") if p.is_dir()) if RUNS.exists() else []:
        rel = str(run_dir).replace("\\", "/")
        meta_path = run_dir / "meta.json"
        if not meta_path.exists():
            report.add("EXP_NO_META", ERROR, f"Запуск {run_dir.name} без meta.json", rel)
            continue
        m = json.loads(meta_path.read_text(encoding="utf-8"))
        ids.add(m["run_id"])
        if m.get("exit_code") != 0:
            report.add("EXP_FAILED", INFO, f"{m['run_id']}: завершился с кодом {m['exit_code']}", rel)
        if m["git"].get("dirty") and not (run_dir / "code.patch").exists() and not m["git"].get("untracked"):
            report.add("EXP_PATCH_MISSING", ERROR, f"{m['run_id']}: дерево было грязным, а патча нет", rel)
        if not m.get("metrics") and not m.get("outputs"):
            report.add("EXP_NO_RESULT", WARNING, f"{m['run_id']}: нет ни метрик, ни выходных файлов", rel,
                       hint="Пишите metrics.json в $GITSCI_RUN_DIR или укажите -o")
    if figures_dir and Path(figures_dir).exists():
        for meta in Path(figures_dir).rglob("*.meta.json"):
            rid = json.loads(meta.read_text(encoding="utf-8")).get("run_id")
            if rid and rid not in ids:
                report.add("EXP_FIGURE_ORPHAN", ERROR, f"График ссылается на запуск {rid}, которого нет",
                           str(meta).replace("\\", "/"))
