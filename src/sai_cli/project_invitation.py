"""Project invitation previews and receipts over the existing invitation owner."""

from argparse import Namespace
from copy import deepcopy
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from .catalog import _boolean, _count, _items, _object
from .contracts import _timestamp_text
from .errors import ContractError
from .invitations import _invitation, _label, invitation_deliveries
from .managed_runs import terminal_log
from .project_compute import _project, reference, request_key
from .render import follow_up_command


_PREVIEW = "project.invitation-preview/v1"
_CREATED = "project.invitation-create/v1"
_DETAIL = "project.invitation/v1"
_ROLES = {"read", "write", "admin"}


def _terms(value: object, *, request_id: str) -> dict[str, Any]:
    row = _object(value)
    ttl = _count(row["ttl_hours"])
    if row["role"] not in _ROLES or ttl is None or not 1 <= ttl <= 720:
        raise ValueError("invalid invitation terms")
    return {"role": row["role"], "compute_enabled": _boolean(row["compute_enabled"]),
            "membership_valid_from": _timestamp_text(row, "membership_valid_from", nullable=True, request_id=request_id),
            "membership_expires_at": _timestamp_text(row, "membership_expires_at", nullable=False, request_id=request_id),
            "ttl_hours": ttl}


@dataclass(frozen=True)
class ProjectInvitation:
    values: dict[str, Any]

    @classmethod
    def parse(cls, payload: object, *, schema: str, request_id: str,
              project_id: str | None = None, site_id: str | None = None,
              username: str | None = None, invitee_id: str | None = None,
              invitation_id: str | None = None, key: str | None = None,
              terms: dict[str, Any] | None = None) -> "ProjectInvitation":
        try:
            data = _object(payload)
            if schema not in {_PREVIEW, _CREATED, _DETAIL} or data["schema_version"] != schema:
                raise ValueError("invalid project invitation contract")
            recipient = _object(data["invitee"])
            invitee = {"user_id": reference(recipient["user_id"]), "username": reference(recipient["username"])}
            if (username is not None and invitee["username"] != username
                    or invitee_id is not None and invitee["user_id"] != invitee_id):
                raise ValueError("invitee mismatch")
            result: dict[str, Any] = {"schema_version": schema, "invitee": invitee}
            if schema == _CREATED:
                if data["state"] != "accepted" or data["delivery"] != "message_center":
                    raise ValueError("invalid invitation creation receipt")
                result.update(state="accepted", request_id=request_key(data["request_id"]),
                              invitation_id=reference(data["invitation_id"]), project_id=reference(data["project_id"]),
                              delivery="message_center")
                if (key is not None and result["request_id"] != key
                        or project_id is not None and result["project_id"] != project_id
                        or invitation_id is not None and result["invitation_id"] != invitation_id):
                    raise ValueError("invitation receipt mismatch")
            else:
                project = _project(data["project"])
                for field in ("label", "organization_label"):
                    _label(project[field])
                if project_id is not None and project["project_id"] != project_id:
                    raise ValueError("project mismatch")
                result["project"] = project
                if schema == _PREVIEW:
                    roles = _items(data["allowed_roles"], maximum=3)
                    if not roles or any(role not in _ROLES for role in roles) or len(set(roles)) != len(roles):
                        raise ValueError("invalid allowed roles")
                    proposed = _terms(data["terms"], request_id=request_id)
                    if proposed["role"] not in roles or terms is not None and proposed != terms:
                        raise ValueError("invitation terms mismatch")
                    if data["relationship_scope"] != "global" or data["delivery"] != "message_center":
                        raise ValueError("invalid invitation scope")
                    selected_site = reference(data["site_id"], site=True)
                    if site_id is not None and selected_site != site_id:
                        raise ValueError("invitation site mismatch")
                    result.update(allowed_roles=list(roles), site_id=selected_site, site_label=_label(data["site_label"]),
                                  relationship_scope="global", delivery="message_center", terms=proposed,
                                  directory_site_labels=[_label(label) for label in _items(data["directory_site_labels"], maximum=64)],
                                  acceptance_expires_at=_timestamp_text(data, "acceptance_expires_at", nullable=False, request_id=request_id))
                else:
                    invitation = _invitation(data["invitation"], request_id)
                    if (invitation["target_kind"] != "project"
                            or invitation_id is not None and invitation["invitation_id"] != invitation_id
                            or site_id is not None and invitation["site_id"] != site_id):
                        raise ValueError("project invitation mismatch")
                    result.update(invitation=invitation,
                                  deliveries=invitation_deliveries(data["deliveries"], request_id=request_id))
            return cls(result)
        except (KeyError, TypeError, ValueError) as exc:
            raise ContractError("The project invitation response is invalid.", request_id=request_id) from exc

    def as_dict(self) -> dict[str, Any]:
        return deepcopy(self.values)


def _date(value: str | None, *, empty: str) -> str:
    return value.replace("T", " ").removesuffix("Z") + " UTC" if value else empty


def render_project_invitation(result: ProjectInvitation, *, args: Namespace) -> str:
    from .messages import display_site_name

    value = result.values
    username = value["invitee"]["username"]
    if value["schema_version"] == _CREATED:
        command = follow_up_command(args, "projects", "invitation", value["invitation_id"])
        return f"邀请已创建：{username} · 消息中心\n查看邀请：{terminal_log(command)}\n"
    preview = value["schema_version"] == _PREVIEW
    project = value["project"]
    terms = value["terms"] if preview else value["invitation"]
    state = "邀请预览" if preview else {"pending": "待接受", "accepted": "已接受", "expired": "已过期", "revoked": "已撤回"}[terms["status"]]
    roles = {"read": "查看文件", "write": "编辑文件", "admin": "项目管理员 · 编辑文件"}
    lines = [f"{project['label']} · {username} · {state}",
             f"权限：{roles[terms['role']]} · " + ("使用项目账户计算" if terms["compute_enabled"] else "不含计算权限")]
    if terms["compute_enabled"]:
        budget = project["uses_project_budget"] if preview else terms["uses_project_budget"]
        lines.append(f"付款组织：{project['organization_label']}" + (" · 受项目预算限制" if budget else ""))
    sites = value["directory_site_labels"] if preview else terms["directory_site_labels"]
    lines += ["范围：整个项目的所有关联站点" + (" · " + ", ".join(sites) if sites else ""),
              "成员期限：" + _date(terms["membership_valid_from"], empty="接受后") + " → "
              + _date(terms["membership_expires_at"], empty="未设截止")]
    if preview:
        lines.append("预计接受截止：" + _date(value["acceptance_expires_at"], empty="未设截止"))
    elif terms["accepted_at"]:
        lines.append("接受时间：" + _date(terms["accepted_at"], empty="未记录"))
    else:
        lines.append("接受截止：" + _date(terms["expires_at"], empty="未设截止"))
    if preview:
        words = ["projects", "invite", project["project_id"], "--username", username,
                 "--role", terms["role"], "--compute", "enabled" if terms["compute_enabled"] else "disabled",
                 "--member-expires-at", terms["membership_expires_at"]]
        if terms["membership_valid_from"]:
            words += ["--member-valid-from", terms["membership_valid_from"]]
        words += ["--invitation-hours", str(terms["ttl_hours"]), "--site", value["site_id"], "--apply",
                  "--invitee-id", value["invitee"]["user_id"], "--request-id", getattr(args, "request_id", None) or str(uuid4())]
        lines.append("确认邀请：" + terminal_log(follow_up_command(args, *words)))
    else:
        task_states = {"queued": "等待执行", "running": "正在执行", "ready": "任务已完成", "expired": "任务已取消", "failed": "需要处理"}
        for task in value["deliveries"]:
            site = display_site_name(task.get("site_label"), task["site_id"], language="zh-CN")
            access = "当前可访问工作空间" if task["workspace_available"] else "当前工作空间访问未确认"
            lines.append(f"{site}：{task_states[task['status']]} · {access}")
        command = follow_up_command(args, "projects", "invitation", terms["invitation_id"])
        lines.append("查看邀请：" + terminal_log(command))
    return "\n".join(lines) + "\n"
