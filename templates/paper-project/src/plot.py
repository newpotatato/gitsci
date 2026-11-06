"""Графики только через gitsci.mpl: стиль лаборатории + метаданные для проверки Check Graphs."""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

import gitsci.mpl as gm  # noqa: E402


def main() -> None:
    gm.use_style()
    fig, ax = plt.subplots(figsize=gm.size("single"))
    ax.plot([0, 1, 2], [0, 1, 4], label="example")
    ax.set_xlabel("iteration")
    ax.set_ylabel("value")
    ax.legend()
    gm.save(fig, "figures/example.pdf")


if __name__ == "__main__":
    main()
