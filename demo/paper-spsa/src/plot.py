"""Рисунок сходимости (Fig. 1) из results/convergence.csv."""

import csv
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

import gitsci.mpl as gm  # noqa: E402

LABELS = {"spsa": "SPSA", "spsa_momentum": "SPSA + momentum"}


def main() -> None:
    with open("results/convergence.csv") as fh:
        rows = list(csv.DictReader(fh))
    gm.use_style()
    fig, ax = plt.subplots(figsize=gm.size("single"))
    for key, label in LABELS.items():
        ax.semilogy([int(r["iter"]) for r in rows], [float(r[key]) for r in rows], label=label)
    ax.set_xlabel("Iteration $k$")
    ax.set_ylabel(r"$\|x_k\|^2$")
    ax.legend()
    gm.save(fig, "figures/convergence.pdf", run_id=os.environ.get("GITSCI_RUN_ID"))


if __name__ == "__main__":
    main()
