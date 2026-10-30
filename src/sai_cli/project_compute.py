"""Typed project/member management results, with no local permission decisions."""
from argparse import Namespace
from dataclasses import dataclass
import re
from typing import Any
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from .catalog import _boolean, _count, _items, _object, _text
from .contracts import _timestamp_text
from .errors import ContractError
from .managed_runs import terminal_log
from .render import follow_up_command


def reference(value: object, *, site: bool = False) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}", value) is None or (
        site and value.casefold() in {"default", "global"}
    ):
        raise ValueError("invalid project reference")
    return value


def request_key(value: object) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[A-Za-z0-9_.:-]{8,128}", value) is None:
        raise ValueError("invalid request key")
    return value


def _project(value: object) -> dict[str, Any]:
    row = _object(value)
    return {"project_id": reference(row["project_id"]), "code": reference(row["code"]),
            "label": _text(row["label"], maximum=256),
            "organization_label": _text(row["organization_label"], maximum=256),
            "compute_supported": _boolean(row["compute_supported"]),
            "uses_project_budget": _boolean(row["uses_project_budget"])}


def _member(value: object, request_id: str) -> dict[str, Any]:
    row = _object(value)
    if row["role"] not in {"owner", "admin", "read", "write"} or row["membership_status"] not in {"active", "scheduled", "expired"}:
        raise ValueError("invalid member state")
    return {"membership_id": reference(row["membership_id"]), "username": reference(row["username"]),
            "role": row["role"], "compute_enabled": _boolean(row["compute_enabled"]),
            "membership_status": row["membership_status"],
            **{key: _timestamp_text(row, key, nullable=True, request_id=request_id) for key in ("valid_from", "expires_at")}}


def _task(value: object) -> dict[str, Any]:
    row = _object(value)
    generation = _count(row["generation"])
    if generation is None or generation < 1:
        raise ValueError("invalid generation")
    return {"task_id": reference(row["task_id"]), "site_id": reference(row["site_id"], site=True),
            "generation": generation}


@dataclass(frozen=True)
class ProjectCompute:
    values: dict[str, Any]

    @classmethod
    def parse(cls, payload: object, *, schema: str, request_id: str, project_id: str | None = None,
              membership_id: str | None = None, site_id: str | None = None, task_id: str | None = None,
              key: str | None = None, limit: int = 100, cursor: str | None = None,
              username: str | None = None) -> "ProjectCompute":
        try:
            data = _object(payload)
            if data["schema_version"] != schema:
                raise ValueError("invalid project contract")
            result = {"schema_version": schema}
            if schema not in {"collaboration.projects/v1", "project.compute-enable/v1"}:
                result["project"] = _project(data["project"])
                if project_id is not None and result["project"]["project_id"] != project_id:
                    raise ValueError("project mismatch")
            if schema in {"collaboration.projects/v1", "project.members/v1"}:
                items = [_project(row) if schema == "collaboration.projects/v1" else _member(row, request_id)
                         for row in _items(data["items"], maximum=limit)]
                field = "project_id" if schema == "collaboration.projects/v1" else "membership_id"
                ids = [row[field] for row in items]
                more = _boolean(data["has_more"])
                following = reference(data["next_cursor"]) if data["next_cursor"] is not None else None
                if ids != sorted(set(ids)) or cursor is not None and any(x <= cursor for x in ids) or (
                    more and (not ids or following != ids[-1]) or not more and following is not None
                ) or username is not None and any(row["username"] != username for row in items):
                    raise ValueError("invalid project page")
                result.update(items=items, has_more=more, next_cursor=following)
            elif schema == "project.member/v1":
                member = _member(data["member"], request_id)
                if member["membership_id"] != membership_id:
                    raise ValueError("member mismatch")
                sites = []
                for raw in _items(data["sites"], maximum=64):
                    row = _object(raw)
                    if row["file_access"] not in {"none", "read", "write"}:
                        raise ValueError("invalid file access")
                    task_url = row.get("task_url")
                    if task_url is not None:
                        task_url = _text(task_url, maximum=256)
                        if not isinstance(task_url, str) or not task_url.startswith("/portal/#/portal/account/operation-records?"):
                            raise ValueError("invalid task URL")
                        query = parse_qs(urlsplit(task_url).fragment.partition("?")[2], strict_parsing=True)
                        if set(query) != {"tab", "task_id"} or query["tab"] != ["background"] or len(query["task_id"]) != 1:
                            raise ValueError("invalid task URL")
                        reference(query["task_id"][0])
                    sites.append({"site_id": reference(row["site_id"], site=True),
                        "site_label": _text(row["site_label"], maximum=256), "status": reference(row["status"]),
                        "file_access": row["file_access"], "compute_access": _boolean(row["compute_access"]),
                        "task_id": reference(row["task_id"]) if row.get("task_id") is not None else None,
                        "task_url": task_url})
                if len({row["site_id"] for row in sites}) != len(sites):
                    raise ValueError("duplicate site")
                reason = data["unavailable_reason"]
                if reason not in {None, "already_enabled", "permission_denied", "member_not_current",
                                  "file_editing_required", "compute_not_supported", "site_unavailable"}:
                    raise ValueError("invalid action reason")
                allowed = _boolean(data["enable_compute_allowed"])
                if allowed != (reason is None):
                    raise ValueError("inconsistent action")
                result.update(member=member, sites=sites, enable_compute_allowed=allowed, unavailable_reason=reason)
            elif schema == "project.compute-enable/v1":
                if data["state"] != "accepted" or key is not None and data["request_id"] != key:
                    raise ValueError("invalid accepted request")
                result.update(state="accepted", request_id=request_key(data["request_id"]),
                    project_id=reference(data["project_id"]), membership_id=reference(data["membership_id"]),
                    tasks=[_task(row) for row in _items(data["tasks"], maximum=64)])
                if not result["tasks"] or len({x["task_id"] for x in result["tasks"]}) != len(result["tasks"]):
                    raise ValueError("invalid request tasks")
                if project_id is not None and result["project_id"] != project_id or membership_id is not None and result["membership_id"] != membership_id:
                    raise ValueError("request target mismatch")
            elif schema == "project.member-task/v1":
                if data["requested_task_id"] != task_id or data["status"] not in {"queued", "running", "ready", "expired", "failed"}:
                    raise ValueError("invalid task state")
                if data["membership_status"] not in {None, "active", "scheduled", "expired"}:
                    raise ValueError("invalid member state")
                result.update(requested_task_id=reference(task_id), task=_task(data["task"]),
                    membership_id=reference(data["membership_id"]), username=reference(data["username"]),
                    status=data["status"], result_code=reference(data["result_code"]),
                    finished_at=_timestamp_text(data, "finished_at", nullable=True, request_id=request_id),
                    compute_enabled=None if data["compute_enabled"] is None else _boolean(data["compute_enabled"]),
                    membership_status=data["membership_status"],
                    can_retry=_boolean(data["can_retry"]))
            else:
                raise ValueError("unsupported project contract")
            if site_id is not None:
                if data["site_id"] != site_id:
                    raise ValueError("site mismatch")
                result["site_id"] = reference(site_id, site=True)
            return cls(result)
        except (KeyError, TypeError, ValueError) as exc:
            raise ContractError("The project management response is invalid.", request_id=request_id) from exc

    def as_dict(self) -> dict[str, Any]:
        from copy import deepcopy
        return deepcopy(self.values)


def render_project_compute(result: ProjectCompute, *, args: Namespace) -> str:
    value = result.values
    if "items" in value:
        if value["schema_version"] == "collaboration.projects/v1":
            lines = [f"{row['label']} · {row['organization_label']} · {row['code']}\n  {row['project_id']}" for row in value["items"]]
        else:
            roles = {"owner": "负责人", "admin": "管理员", "write": "编辑文件", "read": "查看文件"}
            states = {"active": "", "scheduled": " · 尚未生效", "expired": " · 已过期"}
            lines = [f"{row['username']} · {'计算已启用' if row['compute_enabled'] else '计算未启用'} · {roles[row['role']]}{states[row['membership_status']]}\n  {row['membership_id']}" for row in value["items"]]
        if value["has_more"]:
            words = ["projects", args.projects_command]
            if args.projects_command == "members":
                words.extend((args.project_id, "--site", value["site_id"]))
                if args.username:
                    words.extend(("--username", args.username))
            elif args.query:
                words.extend(("--query", args.query))
            lines.append("下一页：" + terminal_log(follow_up_command(args, *words, "--cursor", value["next_cursor"], "--limit", str(args.limit), "--format", "table")))
        return "\n".join(lines or ["暂无匹配项目" if "project" not in value else "暂无匹配成员"]) + "\n"
    if "member" in value:
        member, project = value["member"], value["project"]
        lines = [f"{project['label']} · {member['username']}",
                 "计算许可：" + ("已启用" if member["compute_enabled"] else "未启用"),
                 "作用范围：该项目成员关系的所有关联站点",
                 f"付款组织：{project['organization_label']}" + (" · 受项目预算限制" if project["uses_project_budget"] else "")]
        for site in value["sites"]:
            statuses = {"processing": "正在生效", "pending": "等待生效", "queued": "等待生效", "running": "正在生效",
                        "failed": "需要处理", "expired": "已过期", "scheduled": "尚未生效", "revoked": "已撤销",
                        "not_enabled": "未开通", "unavailable": "状态暂不可用"}
            lines.append(f"{site['site_label']}：" + ("站点计算许可已生效" if site["compute_access"] else
                statuses.get(site["status"], "站点计算许可未生效")))
            if site["task_id"]:
                lines.append("查看进度：" + terminal_log(follow_up_command(args, "projects", "task", site["task_id"], "--format", "table")))
            elif site.get("task_url"):
                lines.append("相关任务：" + site["task_url"])
        if args.projects_command == "enable-compute" and value["enable_compute_allowed"]:
            lines.append("确认启用：" + terminal_log(follow_up_command(args, "projects", "enable-compute", project["project_id"],
                member["membership_id"], "--apply", "--request-id", args.request_id or str(uuid4()),
                "--site", value["site_id"], "--format", "table")))
        elif value["unavailable_reason"] not in {None, "already_enabled"}:
            lines.append({"permission_denied": "无权调整该成员", "member_not_current": "成员关系当前未生效",
                "file_editing_required": "需要现有文件编辑权限", "compute_not_supported": "该项目没有计算账户",
                "site_unavailable": "该站点当前不可用"}[value["unavailable_reason"]])
        return "\n".join(lines) + "\n"
    if "tasks" in value:
        return "计算许可请求已受理\n" + "\n".join("查看进度：" + terminal_log(follow_up_command(args, "projects", "task", row["task_id"], "--format", "table")) for row in value["tasks"]) + "\n"
    status = {"queued": "等待执行", "running": "正在执行", "ready": "任务已完成", "expired": "任务已取消", "failed": "需要处理"}[value["status"]]
    current = "成员关系已不存在" if value["compute_enabled"] is None else "当前许可已启用" if value["compute_enabled"] else "当前许可未启用"
    if value["membership_status"] in {"scheduled", "expired"}:
        current = "成员关系尚未生效" if value["membership_status"] == "scheduled" else "成员关系已过期"
    follow = follow_up_command(args, "projects", "member", value["project"]["project_id"], value["membership_id"],
                               "--site", value["task"]["site_id"], "--format", "table")
    return f"{value['project']['label']} · {value['username']}\n{value['task']['site_id']}：{status} · {current}\n查看当前权限：{terminal_log(follow)}\n"
