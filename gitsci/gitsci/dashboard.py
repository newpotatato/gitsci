"""Сводная таблица по проектам для руководителей: кто закреплён, какие задачи открыты, что просрочено.

Собирается через GitLab API токеном бота и коммитится в README.md закрытого проекта lab/dashboard
(его видят только руководители). Плюс HTML-версия как артефакт.
"""

import base64
import html
from collections import defaultdict
from datetime import date

import yaml

SERVICE = {"ci-templates", "lab-registry", "dashboard", "paper-template", "events"}
ROLES = {10: "Guest", 20: "Reporter", 30: "Developer", 40: "Maintainer", 50: "Owner"}
STATUS_ICON = {"success": "🟢", "failed": "🔴", "running": "🔵", "pending": "⚪", "canceled": "⚫",
               "manual": "⚪", "skipped": "⚪", None: "—"}
PLAN_ORDER = ["planned", "draft_ru", "review_ru", "approved_ru", "draft_en", "done"]


def collect(gl, group, today=None):
    today = today or date.today()
    projects = []
    for p in gl.get_all(f"groups/{gl.pid(group)}/projects", include_subgroups=True, archived=False):
        if p["path"] in SERVICE:
            continue
        pid = p["id"]
        members = [m for m in gl.get_all(f"projects/{pid}/members/all") if m["username"] != "root"
                   and "_bot" not in m["username"]]
        issues = [i for i in gl.get_all(f"projects/{pid}/issues", state="opened")
                  if "событие" not in i.get("labels", [])]  # события — не задачи
        mrs = gl.get_all(f"projects/{pid}/merge_requests", state="opened")
        main = gl.get_all(f"projects/{pid}/pipelines", ref=p.get("default_branch") or "main")[:1]
        plan = _plan(gl, pid, p.get("default_branch") or "main")
        projects.append({
            "name": p["path"], "title": p["name"], "url": p["web_url"],
            "members": [(m["username"], m["name"], ROLES.get(m["access_level"], "?")) for m in members],
            "issues": [{
                "title": i["title"], "url": i["web_url"], "due": i.get("due_date"),
                "assignees": [a["username"] for a in i.get("assignees") or []] or ["—"],
                "overdue": bool(i.get("due_date") and date.fromisoformat(i["due_date"]) < today),
            } for i in issues],
            "mrs": [{"iid": m["iid"], "title": m["title"], "author": m["author"]["username"], "url": m["web_url"],
                     "labels": m.get("labels", [])} for m in mrs],
            "main_status": main[0]["status"] if main else None,
            "plan": plan,
        })
    return projects


def _plan(gl, pid, ref):
    try:
        f = gl.get(f"projects/{pid}/repository/files/plan.yml", ref=ref)
        plan = yaml.safe_load(base64.b64decode(f["content"]).decode("utf-8")) or {}
    except Exception:  # noqa: BLE001 — у проекта может не быть плана
        return None
    sections = plan.get("sections") or []
    done = sum(1 for s in sections if s.get("status") == "done")
    ru_ok = sum(1 for s in sections if s.get("status") in PLAN_ORDER[3:])
    return {"paper": plan.get("paper", ""), "sections": len(sections), "ru_approved": ru_ok, "done": done,
            "statuses": {s.get("id"): s.get("status") for s in sections}}


def markdown(projects, today=None):
    today = today or date.today()
    out = [f"# Сводка по проектам лаборатории\n\n_Обновлено {today}. Видят только руководители._\n",
           "## Проекты\n",
           "| Проект | Статья | Участники | Открытые задачи | Просрочено | Открытые MR | CI main | RU одобрено / готово |",
           "|---|---|---|---|---|---|---|---|"]
    for p in projects:
        people = ", ".join(f"{u} ({r})" for u, _, r in p["members"]) or "—"
        overdue = sum(i["overdue"] for i in p["issues"])
        plan = p["plan"]
        progress = f"{plan['ru_approved']}/{plan['sections']} · {plan['done']}/{plan['sections']}" if plan else "—"
        mrs = "<br>".join(f"[!{m['iid']}]({m['url']}) {m['author']}" for m in p["mrs"]) or "—"
        out.append(f"| [{p['name']}]({p['url']}) | {plan['paper'] if plan else p['title']} | {people} | "
                   f"{len(p['issues'])} | {'⚠️ ' + str(overdue) if overdue else '0'} | {mrs} | "
                   f"{STATUS_ICON.get(p['main_status'], p['main_status'])} | {progress} |")

    by_person = defaultdict(lambda: {"projects": set(), "open": 0, "overdue": 0, "next": None})
    for p in projects:
        for u, _, _ in p["members"]:
            by_person[u]["projects"].add(p["name"])
        for i in p["issues"]:
            for u in i["assignees"]:
                rec = by_person[u]
                rec["open"] += 1
                rec["overdue"] += i["overdue"]
                if i["due"] and not i["overdue"] and (rec["next"] is None or i["due"] < rec["next"]):
                    rec["next"] = i["due"]
    out += ["\n## Люди\n", "| Кто | Проекты | Открытых задач | Просрочено | Ближайший срок |", "|---|---|---|---|---|"]
    for u, r in sorted(by_person.items()):
        if u == "—":
            continue
        out.append(f"| {u} | {', '.join(sorted(r['projects'])) or '—'} | {r['open']} | "
                   f"{'⚠️ ' + str(r['overdue']) if r['overdue'] else '0'} | {r['next'] or '—'} |")
    unassigned = by_person.get("—", {}).get("open", 0)
    if unassigned:
        out.append(f"\n⚠️ Задач без исполнителя: {unassigned}")

    out += ["\n## Открытые задачи\n", "| Срок | Проект | Задача | Исполнитель |", "|---|---|---|---|"]
    rows = [(i["due"] or "9999", p["name"], i) for p in projects for i in p["issues"]]
    for due, name, i in sorted(rows, key=lambda r: (r[0], r[1])):
        mark = "⚠️ " if i["overdue"] else ""
        out.append(f"| {mark}{i['due'] or '—'} | {name} | [{i['title']}]({i['url']}) | {', '.join(i['assignees'])} |")

    out += ["\n## Статусы разделов\n"]
    for p in projects:
        if p["plan"]:
            st = " · ".join(f"{k}: `{v}`" for k, v in p["plan"]["statuses"].items())
            out.append(f"- **{p['name']}** — {st}")
    return "\n".join(out) + "\n"


def to_html(md_text):
    """Простейший рендер таблиц markdown → HTML для артефакта."""
    import re
    body, in_table = [], False
    for line in md_text.splitlines():
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if set("".join(cells)) <= set("-: "):
                continue
            tag = "th" if not in_table else "td"
            if not in_table:
                body.append("<table>")
                in_table = True
            cells = [re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"<a href='\2'>\1</a>", html.escape(c, quote=False))
                     for c in cells]
            body.append("<tr>" + "".join(f"<{tag}>{c}</{tag}>" for c in cells) + "</tr>")
            continue
        if in_table:
            body.append("</table>")
            in_table = False
        if line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            body.append(f"<h{level}>{html.escape(line.lstrip('# '))}</h{level}>")
        elif line.strip():
            body.append(f"<p>{html.escape(line)}</p>")
    if in_table:
        body.append("</table>")
    return ("<!doctype html><meta charset='utf-8'><title>Сводка лаборатории</title><style>"
            "body{font:14px system-ui,sans-serif;margin:24px}table{border-collapse:collapse;margin:8px 0 24px}"
            "td,th{border:1px solid #ddd;padding:6px 8px;vertical-align:top}th{background:#f5f5f7}</style>"
            + "\n".join(body))


def commit_readme(gl, project, text):
    pid = gl.pid(project)
    try:
        gl.get(f"projects/{pid}/repository/files/README.md", ref="main")
        action = "update"
    except Exception:  # noqa: BLE001
        action = "create"
    gl.post(f"projects/{pid}/repository/commits", branch="main",
            commit_message="Сводка: автообновление [skip ci]",
            actions=[{"action": action, "file_path": "README.md", "content": text}])
