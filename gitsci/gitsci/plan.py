"""Принудительный планинг статьи: порционное написание и апрув русской версии.

plan.yml описывает разделы статьи: владельца, сроки и статус. Английский текст раздела нельзя
писать, пока русская версия не одобрена руководителем. Одобрение = статус approved_ru в plan.yml,
внесённый через MR с меткой ru-approved, которую поставил руководитель (проверяется через API).
"""

import re
from datetime import date
from pathlib import Path

import yaml

from .findings import ERROR, INFO, WARNING

STATUSES = ["planned", "draft_ru", "review_ru", "approved_ru", "draft_en", "done"]
APPROVAL_LABEL = "ru-approved"


def _rank(status):
    return STATUSES.index(status) if status in STATUSES else -1


def _date(value):
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _has_text(path):
    if not path.exists():
        return False
    body = "\n".join(line.split("%")[0] for line in path.read_text(encoding="utf-8").splitlines())
    body = re.sub(r"\\(section|subsection|label)\*?\{[^}]*\}", "", body)
    return len(body.split()) > 5


def load(path="plan.yml"):
    return yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}


def check(path, report, today=None, gitlab=None, project=None):
    today = today or date.today()
    rel = str(path).replace("\\", "/")
    plan = load(path)
    base = Path(path).parent
    supervisor = plan.get("supervisor")
    if not supervisor:
        report.add("PLAN_SUPERVISOR", ERROR, "В plan.yml не указан supervisor (кто апрувит RU-версию)", rel)
    sections = plan.get("sections") or []
    if not sections:
        report.add("PLAN_EMPTY", ERROR, "В plan.yml нет разделов: статью пишем порционно, по разделам", rel)

    for s in sections:
        sid = s.get("id", "?")
        status = s.get("status", "planned")
        if _rank(status) < 0:
            report.add("PLAN_STATUS", ERROR, f"{sid}: неизвестный статус {status}", rel,
                       hint=" → ".join(STATUSES))
            continue
        for key in ("owner", "due_ru", "due_en", "ru", "en"):
            if not s.get(key):
                report.add("PLAN_FIELD", ERROR, f"{sid}: не заполнено поле {key}", rel)
        due_ru, due_en = _date(s.get("due_ru")), _date(s.get("due_en"))
        if due_ru and due_en and due_en < due_ru:
            report.add("PLAN_DATES", ERROR, f"{sid}: срок EN ({due_en}) раньше срока RU ({due_ru})", rel)

        ru, en = base / str(s.get("ru", "")), base / str(s.get("en", ""))
        if _rank(status) >= _rank("draft_ru") and s.get("ru") and not ru.exists():
            report.add("PLAN_FILE", ERROR, f"{sid}: статус {status}, но файла {s['ru']} нет", rel)
        if s.get("en") and _has_text(en) and _rank(status) < _rank("approved_ru"):
            report.add("PLAN_EN_BEFORE_APPROVAL", ERROR,
                       f"{sid}: английский текст написан до апрува русской версии (статус {status})",
                       str(s["en"]), hint="Сначала RU → MR с меткой ru-approved от руководителя → потом EN")
        if _rank(status) >= _rank("approved_ru"):
            if not s.get("approved_by"):
                report.add("PLAN_APPROVAL", ERROR, f"{sid}: статус {status} без approved_by", rel)
            elif supervisor and s["approved_by"] != supervisor:
                report.add("PLAN_APPROVAL", ERROR,
                           f"{sid}: апрув от {s['approved_by']}, а апрувит только {supervisor}", rel)
            elif gitlab is not None and gitlab.enabled and project:
                _verify_approval(gitlab, project, s, report, rel)
            else:
                report.add("PLAN_APPROVAL_UNVERIFIED", INFO,
                           f"{sid}: апрув не сверен с GitLab (нет GITSCI_API_TOKEN)", rel)

        if due_ru and today > due_ru and _rank(status) < _rank("review_ru"):
            report.add("PLAN_OVERDUE", WARNING, f"{sid}: RU-версия просрочена (срок {due_ru}, статус {status})",
                       rel)
        if due_en and today > due_en and status != "done":
            report.add("PLAN_OVERDUE", WARNING, f"{sid}: EN-версия просрочена (срок {due_en})", rel)
    return plan


def _verify_approval(gl, project, s, report, rel):
    """Метку ru-approved в указанном MR должен был поставить именно approved_by."""
    sid, mr = s.get("id"), s.get("approved_mr")
    if not mr:
        report.add("PLAN_APPROVAL", ERROR, f"{sid}: не указан approved_mr (номер MR с апрувом)", rel)
        return
    try:
        events = gl.get_all(f"projects/{gl.pid(project)}/merge_requests/{mr}/resource_label_events")
    except Exception as e:  # noqa: BLE001 — сеть/права: сообщаем, а не падаем
        report.add("PLAN_APPROVAL_UNVERIFIED", WARNING, f"{sid}: не удалось проверить MR !{mr}: {e}", rel)
        return
    ok = any(ev.get("action") == "add" and (ev.get("label") or {}).get("name") == APPROVAL_LABEL
             and (ev.get("user") or {}).get("username") == s["approved_by"] for ev in events)
    if not ok:
        report.add("PLAN_APPROVAL_FORGED", ERROR,
                   f"{sid}: в MR !{mr} метку {APPROVAL_LABEL} ставил не {s['approved_by']}", rel,
                   hint="Апрув засчитывается, только если метку поставил руководитель")


def sync_issues(path, gl, project):
    """plan.yml → задачи GitLab: по задаче на RU и EN каждого раздела, со сроком и исполнителем."""
    plan = load(path)
    if str(plan.get("paper", "")).startswith("TODO"):
        return []  # шаблон: план ещё не заполнен, задачи не создаём
    pid = gl.pid(project)
    users = {}
    existing = {i["title"]: i for i in gl.get_all(f"projects/{pid}/issues", state="all")}
    milestone_id = None
    if plan.get("milestone"):
        ms = {m["title"]: m for m in gl.get_all(f"projects/{pid}/milestones")}
        m = ms.get(plan["milestone"]["title"]) or gl.post(
            f"projects/{pid}/milestones", title=plan["milestone"]["title"],
            due_date=str(plan["milestone"].get("due", "")) or None)
        milestone_id = m["id"]
    done = []
    for s in plan.get("sections") or []:
        owner = s.get("owner")
        if owner and owner not in users:
            found = gl.get("users", username=owner)
            users[owner] = found[0]["id"] if found else None
        for stage, due, finished in (("RU", s.get("due_ru"), _rank(s.get("status")) >= _rank("approved_ru")),
                                     ("EN", s.get("due_en"), s.get("status") == "done")):
            title = f"[{stage}] {s.get('title', s.get('id'))}"
            data = {
                "title": title,
                "due_date": str(due) if due else None,
                "labels": f"paper,section::{s.get('id')},stage::{stage.lower()}",
                "assignee_ids": [users[owner]] if users.get(owner) else [],
                "milestone_id": milestone_id,
                "description": f"Раздел `{s.get('id')}` из plan.yml.\n\nФайл: `{s.get(stage.lower())}`\n\n"
                               + ("RU-версию одобряет руководитель меткой ~ru-approved в MR." if stage == "RU"
                                  else "Пишется только после апрува RU-версии."),
            }
            if title in existing:
                issue = gl.put(f"projects/{pid}/issues/{existing[title]['iid']}",
                               **data, state_event="close" if finished else "reopen")
            else:
                issue = gl.post(f"projects/{pid}/issues", **data)
                if finished:
                    gl.put(f"projects/{pid}/issues/{issue['iid']}", state_event="close")
            done.append(issue["web_url"])
    return done
