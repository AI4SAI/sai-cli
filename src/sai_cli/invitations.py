"""Recipient invitation and access-task views, independent of native queries."""

from dataclasses import dataclass
from argparse import Namespace
import re
from typing import Any

from .catalog import _boolean, _count, _items, _object, _text, _token
from .contracts import ACCOUNT_VERIFICATION_PATH, _timestamp_text
from .errors import ContractError
from .render import follow_up_command
from .managed_runs import terminal_log


def invitation_reference(value: object, *, site: bool = False) -> str:
    text = _token(value)
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}", text) is None or (
        site and text.casefold() in {"default", "global"}
    ):
        raise ValueError("invalid invitation reference")
    return text


def _label(value: object) -> str:
    text = _text(value, maximum=1200, empty=True)
    if any(ord(character) < 32 or 127 <= ord(character) < 160 for character in text):
        raise ValueError("invalid invitation label")
    return text


def _invitation(value: object, request_id: str) -> dict[str, Any]:
    row = _object(value)
    kind, role, status = row["target_kind"], row["role"], row["status"]
    roles = {"organization": {"member", "admin"}, "project": {"read", "write", "admin"}, "directory": {"read", "write"}}
    if kind not in roles or role not in roles[kind] or status not in {"pending", "accepted", "expired", "revoked"}:
        raise ValueError("invalid invitation state")
    scope = "directory" if kind == "directory" else "global"
    if row["relationship_scope"] != scope:
        raise ValueError("invalid invitation scope")
    result = {"invitation_id": invitation_reference(row["invitation_id"]), "status": status,
              "target_kind": kind, "target_label": _label(row["target_label"]),
              "role": role, "site_id": invitation_reference(row["site_id"], site=True),
              "site_label": _label(row["site_label"]), "relationship_scope": scope,
              "directory_site_labels": [_label(value) for value in _items(row["directory_site_labels"], maximum=64)],
              "has_compute_resources": _boolean(row["has_compute_resources"]),
              "compute_enabled": _boolean(row["compute_enabled"]),
              "uses_project_budget": _boolean(row["uses_project_budget"])}
    result.update({field: _timestamp_text(row, field, nullable=True, request_id=request_id) for field in (
        "membership_valid_from", "membership_expires_at", "expires_at", "accepted_at",
    )})
    return result


@dataclass(frozen=True)
class Invitations:
    values: dict[str, Any]

    @classmethod
    def page(cls, payload: object, *, limit: int, cursor: str | None, request_id: str) -> "Invitations":
        try:
            data = _object(payload)
            if data.get("schema_version") != "collaboration.invitations/v2":
                raise ContractError("Invitation versions do not match. Update the paired Portal and CLI before accepting.",
                                    code="invitation_contract_version", request_id=request_id)
            items = [_invitation(row, request_id) for row in _items(data["items"], maximum=limit)]
            ids = [row["invitation_id"] for row in items]
            count, more = _count(data["count"]), _boolean(data["has_more"])
            following = None if data["next_cursor"] is None else invitation_reference(data["next_cursor"])
            if (ids != sorted(set(ids)) or count != len(items) or
                any(row["status"] != "pending" for row in items) or
                cursor is not None and any(value <= cursor for value in ids) or
                more and (not ids or following != ids[-1]) or not more and following is not None):
                raise ValueError("invalid invitation page scope")
            return cls({"schema_version": data["schema_version"], "items": items, "count": count,
                        "has_more": more, "next_cursor": following})
        except (KeyError, TypeError, ValueError) as exc:
            raise ContractError("The invitation page is invalid.", request_id=request_id) from exc

    @classmethod
    def detail(cls, payload: object, *, invitation_id: str, request_id: str) -> "Invitations":
        try:
            data = _object(payload)
            if data.get("schema_version") != "collaboration.invitation/v2":
                raise ContractError("Invitation versions do not match. Update the paired Portal and CLI before accepting.",
                                    code="invitation_contract_version", request_id=request_id)
            item = _invitation(data["invitation"], request_id)
            if item["invitation_id"] != invitation_id:
                raise ValueError("invitation mismatch")
            action = data["next_action"]
            if action not in {"accept", "complete_identity_assurance", "observe", "none"}:
                raise ValueError("invalid next action")
            verification_url = data.get("verification_url")
            if verification_url is not None and (
                verification_url != ACCOUNT_VERIFICATION_PATH or action != "complete_identity_assurance"
            ):
                raise ValueError("invalid invitation verification URL")
            deliveries = []
            for value in _items(data["deliveries"], maximum=64):
                row = _object(value)
                generation = _count(row["generation"])
                if generation is None or generation < 1 or row["status"] not in {"queued", "running", "ready", "expired", "failed"}:
                    raise ValueError("invalid invitation task")
                deliveries.append({"task_id": invitation_reference(row["task_id"]), "generation": generation,
                                   "site_id": invitation_reference(row["site_id"], site=True), "status": row["status"],
                                   "finished_at": _timestamp_text(row, "finished_at", nullable=True, request_id=request_id),
                                   "workspace_available": _boolean(row["workspace_available"])})
            if len({row["task_id"] for row in deliveries}) != len(deliveries):
                raise ValueError("duplicate invitation task")
            return cls({"schema_version": data["schema_version"], "invitation": item,
                        "next_action": action, "deliveries": deliveries, "verification_url": verification_url})
        except (KeyError, TypeError, ValueError) as exc:
            raise ContractError("The invitation response is invalid.", request_id=request_id) from exc

    def as_dict(self) -> dict[str, Any]:
        from copy import deepcopy
        return deepcopy(self.values)


def _permission_label(row: dict[str, Any]) -> str:
    kind = row["target_kind"]
    labels = []
    if kind == "organization":
        labels.append("组织管理员" if row["role"] == "admin" else "正式组织成员")
    else:
        if row["role"] == "admin":
            labels.append("项目管理员")
        labels.append("查看文件" if row["role"] == "read" else "编辑文件")
    if row["compute_enabled"]:
        labels.append("使用组织账户计算" if kind == "organization" else "使用项目账户计算")
        payer = "本组织" if kind == "organization" else "所属组织"
        labels.append(f"计算费用由{payer}承担" + ("，并受本项目预算限制" if row["uses_project_budget"] else ""))
    else:
        labels.append("不含计算权限")
    return " · ".join(labels)


def render_invitations(result: Invitations, *, args: Namespace | None = None) -> str:
    value = result.values
    states = {"pending": "待接受", "accepted": "已接受", "expired": "已过期", "revoked": "已撤回"}
    if "items" in value:
        lines = [f"{row['target_label']} · {_permission_label(row)} · {row['site_label']}\n"
                 f"  接受截止 {row['expires_at'] or '未指定'} · {row['invitation_id']}" for row in value["items"]]
        if value["has_more"]:
            command = follow_up_command(args, "invitations", "list", "--cursor", value["next_cursor"],
                                        "--limit", str(getattr(args, "limit", 50)), "--format", "table")
            lines.append("下一页：" + terminal_log(command))
        return "\n".join(lines or ["暂无待接受邀请"]) + "\n"
    row = value["invitation"]
    sites = ", ".join(row["directory_site_labels"]) if row["target_kind"] == "directory" else row["site_label"]
    lines = [f"{row['target_label']} · {states[row['status']]}",
             f"权限：{_permission_label(row)}",
             f"协作期限：{row['membership_valid_from'] or '接受后'} → {row['membership_expires_at'] or '未设截止'}",
             f"范围：{'全局关系' if row['relationship_scope'] == 'global' else '目录访问'} · {sites}"]
    task_states = {"queued": "等待执行", "running": "正在执行", "ready": "任务已完成", "expired": "任务已取消", "failed": "需要处理"}
    for task in value["deliveries"]:
        lines.append(f"{task['site_id']}：{task_states[task['status']]} · " + ("当前可访问工作空间" if task['workspace_available'] else "尚未确认当前工作空间可访问"))
    if value["next_action"] == "complete_identity_assurance":
        lines.append("身份认证：" + value["verification_url"] if value.get("verification_url") else "请在控制台完成身份认证")
    elif value["next_action"] == "accept":
        lines.append(f"接受截止：{row['expires_at'] or '未指定'}")
        if row["target_kind"] == "organization":
            lines.append("保留已有有效的默认计算账户；没有时才将本组织设为默认")
        if args is not None and args.invitations_command == "accept" and not args.apply:
            command = follow_up_command(args, "invitations", "accept", row["invitation_id"], "--apply", "--format", "table")
            lines.append("确认接受：" + terminal_log(command))
    if value["next_action"] in {"complete_identity_assurance", "observe"}:
        command = follow_up_command(args, "invitations", "show", row["invitation_id"], "--format", "table")
        lines.append("查看进度：" + terminal_log(command))
    return "\n".join(lines) + "\n"
