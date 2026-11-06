"""Стиль графиков лаборатории для matplotlib и сохранение с метаданными для проверки.

    import gitsci.mpl as gm
    gm.use_style()
    fig, ax = plt.subplots(figsize=gm.size("single"))
    ...
    gm.save(fig, "figures/loss.pdf", run_id=os.environ.get("GITSCI_RUN_ID"))
"""

import json
import os
from importlib import resources
from pathlib import Path

# Ширина колонки/полосы в дюймах (Springer Nature: 84 мм и 174 мм).
WIDTHS = {"single": 3.3, "onehalf": 5.0, "double": 6.85}
OKABE_ITO = ["#0072B2", "#E69F00", "#009E73", "#D55E00", "#CC79A7", "#56B4E9", "#F0E442", "#000000"]


def use_style():
    import matplotlib.pyplot as plt
    plt.style.use(str(resources.files("gitsci.data").joinpath("lab.mplstyle")))


def size(kind="single", ratio=0.68):
    w = WIDTHS[kind]
    return (w, w * ratio)


def describe(fig):
    """Шрифты (pt в итоговом размере) и цвета серий фигуры."""
    from matplotlib.colors import to_hex
    from matplotlib.text import Text

    fig.canvas.draw()
    fonts = [{"text": t.get_text(), "size": float(t.get_fontsize())}
             for t in fig.findobj(Text) if t.get_visible() and t.get_text().strip()]
    colors = []
    for ax in fig.axes:
        for line in ax.get_lines():
            if line.get_visible() and not line.get_label().startswith("_child"):
                colors.append(to_hex(line.get_color()))
        for coll in ax.collections:
            fc = coll.get_facecolor()
            if len(fc):
                colors.append(to_hex(fc[0]))
        for cont in ax.containers:
            patches = getattr(cont, "patches", None) or []
            if patches:
                colors.append(to_hex(patches[0].get_facecolor()))
    w, h = fig.get_size_inches()
    return {"fonts": fonts, "series_colors": colors, "width_in": float(w), "height_in": float(h)}


def save(fig, path, run_id=None, **kwargs):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    meta = describe(fig)
    meta["run_id"] = run_id or os.environ.get("GITSCI_RUN_ID")
    kwargs.setdefault("bbox_inches", "tight")
    if path.suffix.lower() in (".png", ".jpg", ".tif", ".tiff"):
        kwargs.setdefault("dpi", 600)
    fig.savefig(path, **kwargs)
    path.with_suffix(".meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return path
