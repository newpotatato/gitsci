"""Check Graphs: стиль графиков.

Две части:
1. Сохранение графика через gitsci.mpl.save() пишет рядом <имя>.meta.json: размеры шрифтов
   в итоговом размере, цвета серий, размер фигуры, id эксперимента.
2. Эта проверка читает метаданные и детерминированно проверяет: шрифт не меньше порога,
   цвета различимы при дальтонизме (симуляция Machado et al. 2009), ширина под колонку журнала.
   Для растровых картинок без метаданных — только разрешение.
"""

import json
from pathlib import Path

import numpy as np

from .findings import ERROR, INFO, WARNING

# Machado, Oliveira, Fernandes (2009), severity = 1.0; применяются к линейному RGB.
CVD = {
    "протанопия": np.array([[0.152286, 1.052583, -0.204868], [0.114503, 0.786281, 0.099216],
                            [-0.003882, -0.048116, 1.051998]]),
    "дейтеранопия": np.array([[0.367322, 0.860646, -0.227968], [0.280085, 0.672501, 0.047413],
                              [-0.011820, 0.042940, 0.968881]]),
    "тританопия": np.array([[1.255528, -0.076749, -0.178779], [-0.078411, 0.930809, 0.147602],
                            [0.004733, 0.691367, 0.303900]]),
}
RASTER = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}
VECTOR = {".pdf", ".svg", ".eps"}


def hex_to_rgb(color):
    color = color.lstrip("#")[:6]
    return np.array([int(color[i:i + 2], 16) for i in (0, 2, 4)]) / 255.0


def _to_linear(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _lab(linear_rgb):
    m = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = m @ np.clip(linear_rgb, 0, 1) / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.array([116 * f[1] - 16, 500 * (f[0] - f[1]), 200 * (f[1] - f[2])])


def min_distance(colors, matrix=None):
    """Минимальное попарное ΔE (CIE76) между цветами, опционально после симуляции CVD."""
    labs = []
    for c in colors:
        lin = _to_linear(hex_to_rgb(c))
        labs.append(_lab(matrix @ lin if matrix is not None else lin))
    best = (float("inf"), None)
    for i in range(len(labs)):
        for j in range(i + 1, len(labs)):
            d = float(np.linalg.norm(labs[i] - labs[j]))
            if d < best[0]:
                best = (d, (colors[i], colors[j]))
    return best


def check(fig_dir, report, cfg):
    fig_dir = Path(fig_dir)
    min_font = cfg.get("min_font_pt", 7)
    min_de = cfg.get("min_color_delta_e", 12)
    max_width = cfg.get("max_width_in", 7.2)
    min_px = cfg.get("min_raster_width_px", 1500)
    if not fig_dir.exists():
        return
    for path in sorted(p for p in fig_dir.rglob("*") if p.suffix.lower() in RASTER | VECTOR):
        rel = str(path).replace("\\", "/")
        meta_path = path.with_suffix(".meta.json")
        if path.suffix.lower() in RASTER:
            try:
                from PIL import Image
                with Image.open(path) as im:
                    width = im.size[0]
                if width < min_px:
                    report.add("FIG_LOW_RES", WARNING, f"Растровый рисунок шириной {width}px (< {min_px})", rel,
                               hint="Сохраняйте в PDF/SVG или с dpi ≥ 300")
            except Exception as e:  # noqa: BLE001
                report.add("FIG_UNREADABLE", ERROR, f"Не читается: {e}", rel)
        if not meta_path.exists():
            report.add("FIG_NO_META", INFO, "График сохранён не через gitsci.mpl.save — стиль не проверен", rel)
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        small = [f for f in meta.get("fonts", []) if f["size"] < min_font]
        if small:
            worst = min(small, key=lambda f: f["size"])
            report.add("FIG_FONT_SMALL", ERROR,
                       f"{len(small)} подпис(ей) мельче {min_font} pt (минимум {worst['size']:.1f} pt: «{worst['text'][:30]}»)",
                       rel, hint="Увеличьте шрифт или уменьшите figsize — проверка в итоговом размере")
        if meta.get("width_in", 0) > max_width:
            report.add("FIG_TOO_WIDE", WARNING, f"Ширина {meta['width_in']:.1f}″ больше полосы {max_width}″", rel)
        colors = sorted(set(meta.get("series_colors", [])))
        if len(colors) >= 2:
            d, pair = min_distance(colors)
            if d < min_de:
                report.add("FIG_COLORS_SIMILAR", WARNING, f"Цвета {pair[0]} и {pair[1]} плохо различимы (ΔE={d:.0f})",
                           rel)
            for name, matrix in CVD.items():
                d, pair = min_distance(colors, matrix)
                if d < min_de:
                    report.add("FIG_CVD", ERROR,
                               f"При {name} цвета {pair[0]} и {pair[1]} неразличимы (ΔE={d:.0f} < {min_de})", rel,
                               hint="Возьмите палитру Okabe–Ito (gitsci.mpl.use_style()) или добавьте маркеры/штрихи")
        if cfg.get("require_run_id") and not meta.get("run_id"):
            report.add("FIG_NO_RUN", WARNING, "График не привязан к эксперименту (run_id)", rel,
                       hint="gitsci.mpl.save(fig, path, run_id=...) — из какого запуска данные")
