"""Эксперимент. Запускать через снимок: gitsci exp run -n <имя> -- python src/experiment.py

Метрики пишутся в $GITSCI_RUN_DIR/metrics.json и попадают в историю запусков.
"""

import json
import os
from pathlib import Path

import numpy as np

from model import objective


def main() -> None:
    rng = np.random.default_rng(0)
    x = rng.normal(size=5)
    result = {"f_value": objective(x)}
    print(result)
    run_dir = Path(os.environ.get("GITSCI_RUN_DIR", "."))
    (run_dir / "metrics.json").write_text(json.dumps(result), encoding="utf-8")


if __name__ == "__main__":
    main()
