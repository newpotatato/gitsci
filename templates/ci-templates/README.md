# ci-templates — общий CI лаборатории

- `paper.gitlab-ci.yml` — проекты статей: latex, bib, figures, plan, experiments, code, plan-sync, pdf.
- `registry.gitlab-ci.yml` — реестр участников: проверка, таблица, напоминания.

Все задания используют образ `gitsci:latest` (пакет `gitsci`). Замечания попадают в виджет Code Quality в MR.
Переменная группы `GITSCI_API_TOKEN` (masked) нужна для сверки авторов, проверки апрува и создания задач.
