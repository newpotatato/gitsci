"""Минимальный клиент GitLab REST API (v4) для CI-проверок и синхронизации плана."""

import os
from urllib.parse import quote

import requests


class GitLab:
    def __init__(self, url=None, token=None, oauth=False):
        # GITSCI_GITLAB_URL — адрес GitLab изнутри сети CI (в локальном демо это http://gitlab:8929,
        # а CI_API_V4_URL указывает на localhost, недоступный из контейнера задания).
        base = url or os.environ.get("GITSCI_GITLAB_URL") or os.environ.get("GITLAB_URL")
        self.api = base.rstrip("/") + "/api/v4" if base else os.environ.get(
            "CI_API_V4_URL", "http://localhost:8929/api/v4")
        self.token = token or os.environ.get("GITSCI_API_TOKEN") or os.environ.get("GITLAB_TOKEN")
        self.s = requests.Session()
        if self.token and oauth:  # токен пользователя из OAuth (портал): действуем с его правами
            self.s.headers["Authorization"] = f"Bearer {self.token}"
        elif self.token:
            self.s.headers["PRIVATE-TOKEN"] = self.token

    @property
    def enabled(self):
        return bool(self.token)

    def _url(self, path):
        return f"{self.api}/{path.lstrip('/')}"

    def get(self, path, **params):
        r = self.s.get(self._url(path), params=params, timeout=30)
        r.raise_for_status()
        return r.json()

    def get_all(self, path, **params):
        out, page = [], 1
        while True:
            r = self.s.get(self._url(path), params={**params, "per_page": 100, "page": page}, timeout=30)
            r.raise_for_status()
            out.extend(r.json())
            if not r.headers.get("X-Next-Page"):
                return out
            page += 1

    def post(self, path, **data):
        r = self.s.post(self._url(path), json=data, timeout=60)
        r.raise_for_status()
        return r.json()

    def put(self, path, **data):
        r = self.s.put(self._url(path), json=data, timeout=60)
        r.raise_for_status()
        return r.json()

    @staticmethod
    def pid(project):
        return quote(str(project), safe="") if not str(project).isdigit() else str(project)
