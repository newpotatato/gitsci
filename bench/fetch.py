"""Скачивает исходники статей корпуса с arXiv в bench/corpus/<id>/ (без запуска чего-либо из архивов)."""

import gzip
import io
import sys
import tarfile
import time
from pathlib import Path

import requests

# Популярные статьи из разных областей: ML, CV, NLP, оптимизация, статистика, безопасность, физика, математика.
PAPERS = {
    "1706.03762": "Attention Is All You Need",
    "1512.03385": "Deep Residual Learning (ResNet)",
    "1409.0473": "Neural Machine Translation by Jointly Learning to Align and Translate",
    "1810.04805": "BERT",
    "1406.2661": "Generative Adversarial Nets",
    "2006.11239": "Denoising Diffusion Probabilistic Models",
    "1312.6114": "Auto-Encoding Variational Bayes",
    "1505.04597": "U-Net",
    "1603.02754": "XGBoost",
    "1801.01203": "Spectre Attacks",
    "1801.00862": "Preskill: Quantum Computing in the NISQ era",
    "math/0211159": "Perelman: The entropy formula for the Ricci flow",
}
ROOT = Path(__file__).parent / "corpus"


def fetch(arxiv_id):
    out = ROOT / arxiv_id.replace("/", "_")
    if out.exists():
        return out
    data = requests.get(f"https://arxiv.org/e-print/{arxiv_id}", timeout=60,
                        headers={"User-Agent": "gitsci-bench/0.1"}).content
    out.mkdir(parents=True)
    try:
        with tarfile.open(fileobj=io.BytesIO(data)) as tar:
            tar.extractall(out, filter="data")  # безопасная распаковка: без абсолютных путей и ссылок
    except tarfile.ReadError:
        raw = gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data
        (out / "main.tex").write_bytes(raw)  # одиночный .tex без архива
    return out


if __name__ == "__main__":
    ids = sys.argv[1:] or list(PAPERS)
    for i, arxiv_id in enumerate(ids):
        print(arxiv_id, fetch(arxiv_id))
        if i + 1 < len(ids):
            time.sleep(3)  # вежливо к arXiv
