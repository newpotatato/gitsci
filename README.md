# gitsci: проверка научных рукописей в репозитории


## Состав

| Путь | Что это |
|---|---|
| `gitsci/` | инструмент: правила, профили журналов (`gitsci/gitsci/profiles/`), каталог правил (`gitsci/gitsci/data/ontology.yml`), тесты |
| `templates/` | шаблон проекта статьи, шаблоны CI для GitLab, синтетический реестр авторов |
| `bench/` | скрипты эксперимента, разметка замечаний и результаты |
| `docs/paper/requirements.md` | каталог из 46 требований журналов с источниками и оценкой автоматизируемости |
| `docs/paper/benchmark.md` | описание эксперимента и полученных чисел |
| `docs/paper/annotation/` | листы для независимой разметки (без ответов первого разметчика) |

## Установка и запуск

```
pip install -e gitsci
gitsci profiles
gitsci --config gitsci.yml latex
python -m pytest gitsci/tests
```

## Воспроизведение эксперимента

Исходники статей arXiv в репозиторий не входят. Списки идентификаторов: `PAPERS` в `bench/fetch.py`
(настроечная выборка, 12 статей) и в `bench/holdout.py` (отложенная выборка, 12 статей).

```
python bench/fetch.py      # скачать настроечную выборку в bench/corpus/
python bench/run.py        # внесённые ошибки и сравнение с chktex, lacheck, TeXtidote
python bench/holdout.py    # отложенная выборка, сравнение с журналом сборки, chklref и TeXtidote
python bench/scenarios.py  # межартефактные и процессные правила на синтетическом проекте
```

Для сравнения нужны chktex, lacheck, chklref и pdflatex в `PATH`; TeXtidote (`textidote.jar`) скачивается
отдельно с https://github.com/sylvainhalle/textidote в `bench/tools/`.

## Лицензия

MIT, см. `LICENSE`.
