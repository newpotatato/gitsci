# Результаты: сценарии на проекте статьи

Чистый проект: 0 замечаний gitsci (без info). Сценариев: 24.

| Сценарий | Ожидаемое правило | gitsci | chktex | lacheck | textidote_sh | textidote_lt |
|---|---|---|---|---|---|---|
| X_author_misspelled | AUTH_NAME_SPELLING | да | нет | нет | нет | нет |
| X_author_not_in_registry | AUTH_NOT_IN_REGISTRY | да | нет | нет | нет | нет |
| X_email_not_in_registry | AUTH_EMAIL | да | нет | нет | нет | нет |
| X_affiliation_mismatch | AUTH_AFFILIATION | да | нет | нет | нет | нет |
| X_registry_stale | AUTH_REGISTRY_STALE | да | нет | нет | нет | нет |
| X_orcid_typo | REG_ORCID_CHECKSUM | да | нет | нет | нет | нет |
| X_self_citation | BIB_SELF_CITATION | да | нет | нет | нет | нет |
| X_figure_orphan_run | EXP_FIGURE_ORPHAN | да | нет | нет | нет | нет |
| X_figure_without_run | FIG_NO_RUN | да | нет | нет | нет | нет |
| X_run_dirty_no_patch | EXP_PATCH_MISSING | да | нет | нет | нет | нет |
| X_figure_cvd | FIG_CVD | да | нет | нет | нет | нет |
| P_en_before_approval | PLAN_EN_BEFORE_APPROVAL | да | нет | нет | нет | нет |
| P_approval_forged | PLAN_APPROVAL_FORGED | да | нет | нет | нет | нет |
| P_approval_by_student | PLAN_APPROVAL | да | нет | нет | нет | нет |
| D_no_ai_declaration | FMT_DECLARATION_MISSING | да | нет | нет | нет | нет |
| D_keywords_semicolons | FMT_KEYWORDS_FORMAT | да | нет | нет | нет | нет |
| D_too_many_pages | FMT_PAGES | да | нет | нет | нет | нет |
| D_sorted_bibliography | FMT_CITE_ORDER | да | нет | нет | нет | нет |
| D_too_few_refs | BIB_TOO_FEW | да | нет | нет | нет | нет |
| D_old_refs | BIB_NOT_RECENT | да | нет | нет | нет | нет |
| D_section_missing | FMT_SECTION_MISSING | да | нет | нет | нет | нет |
| D_long_abstract | FMT_ABSTRACT_LENGTH | да | нет | нет | нет | нет (побочное замечание) |
| D_long_title | FMT_TITLE | да | нет | нет | нет | нет |
| D_forbidden_package | FMT_PACKAGE_FORBIDDEN | да | нет (побочное замечание) | нет | нет (побочное замечание) | нет (побочное замечание) |

| Группа | Сценариев | gitsci | chktex | lacheck | textidote_sh | textidote_lt |
|---|---|---|---|---|---|---|
| Между артефактами | 11 | 11/11 | 0/11 | 0/11 | 0/11 | 0/11 |
| Процесс (план и апрув) | 3 | 3/3 | 0/3 | 0/3 | 0/3 | 0/3 |
| Документ (набор для статьи) | 10 | 10/10 | 0/10 | 0/10 | 0/10 | 0/10 |

## Время, секунды на статью (среднее из 3 прогонов)

| Статья | gitsci | chktex | lacheck | textidote_sh | textidote_lt |
|---|---|---|---|---|---|
| 1312.6114 | 0.04 | 0.55 | 0.48 | 0.74 | 11.02 |
| 1406.2661 | 0.04 | 0.49 | 0.46 | 0.84 | 9.11 |
| 1409.0473 | 0.04 | 0.53 | 0.50 | 0.64 | 14.29 |
| 1505.04597 | 0.02 | 0.55 | 0.56 | 0.55 | 8.69 |
| 1512.03385 | 0.04 | 0.48 | 0.48 | 0.96 | 11.94 |
| 1603.02754 | 0.10 | 0.53 | 0.49 | 0.88 | 11.92 |
| 1706.03762 | 0.03 | 0.44 | 0.48 | 0.64 | 19.86 |
| 1801.00862 | 0.02 | 0.50 | 0.49 | 0.70 | 15.53 |
| 1801.01203 | 0.03 | 0.51 | 0.47 | 0.78 | 13.26 |
| 1810.04805 | 0.04 | 0.59 | 0.52 | 0.60 | 26.09 |
| 2006.11239 | 0.19 | 0.53 | 0.50 | 1.35 | 13.30 |
| math_0211159 | 0.14 | 0.61 | 0.68 | 1.80 | 36.78 |
| project_full | 0.04 |  |  |  |  |
