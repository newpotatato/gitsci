# Образ для CI-заданий Git for Science
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/gitsci
COPY pyproject.toml ./
COPY gitsci ./gitsci
RUN pip install --no-cache-dir . ruff
WORKDIR /builds
CMD ["gitsci", "--help"]
