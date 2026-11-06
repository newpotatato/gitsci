"""Сравнение SPSA и SPSA с моментом на зашумлённой квадратичной функции.

Запуск: gitsci exp run -n momentum -o "results/*.csv" -- python src/experiment.py
"""

import csv
import json
import os
from functools import partial
from pathlib import Path

import numpy as np

from model import noisy_quadratic, spsa

DIM, ITERS, SEEDS = 10, 300, 20


def main() -> None:
    curves = {"spsa": [], "spsa_momentum": []}
    for seed in range(SEEDS):
        for name, beta in (("spsa", 0.0), ("spsa_momentum", 0.6)):
            rng = np.random.default_rng(seed)
            f = partial(noisy_quadratic, rng=rng)
            x0 = np.full(DIM, 2.0)
            curves[name].append(spsa(f, x0, ITERS, rng, beta=beta))
    Path("results").mkdir(exist_ok=True)
    with open("results/convergence.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["iter", *curves])
        means = {k: np.mean(v, axis=0) for k, v in curves.items()}
        for i in range(ITERS):
            w.writerow([i, *(f"{means[k][i]:.6f}" for k in curves)])
    metrics = {k: round(float(np.mean([c[-1] for c in v])), 5) for k, v in curves.items()}
    print(metrics)
    run_dir = Path(os.environ.get("GITSCI_RUN_DIR", "."))
    (run_dir / "metrics.json").write_text(json.dumps(metrics), encoding="utf-8")


if __name__ == "__main__":
    main()
