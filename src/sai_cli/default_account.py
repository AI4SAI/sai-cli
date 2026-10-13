"""Allowlisted default-account intent and site receipts, independent of Pilot."""
from __future__ import annotations

from copy import deepcopy
from argparse import Namespace
from dataclasses import dataclass
import re
from typing import Any

from .catalog import _count, _items, _object, _token
from .contracts import _timestamp_text
from .errors import ContractError


def _account_id(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}", value) is None:
        raise ValueError("invalid account ID")
    return value


def _projection(value: object) -> dict[str, Any]:
    row = _object(value)
    generation = _count(row["generation"])
    task = None if row["task_id"] is None else _token(row["task_id"])
    if (generation is None) != (task is None) or generation is not None and generation < 1:
        raise ValueError("invalid projection generation")
    return {"site_id": _token(row["site_id"]), "task_id": task, "generation": generation}


@dataclass(frozen=True)
class DefaultAccountState:
    values: dict[str, Any]

    @classmethod
    def from_payload(cls, payload: object, *, site_id: str, request_id: str) -> DefaultAccountState:
        try:
            data = _object(payload)
            if data["schema_version"] != "account.defaults/v1" or data["scope"] != "user" or data["site_id"] != site_id:
                raise ValueError("default account scope mismatch")
            choices = []
            for raw in _items(data["choices"], maximum=500):
                row = _object(raw)
                if row["kind"] not in {"personal", "org", "project"} or row["id"] is None:
                    raise ValueError("invalid account choice")
                choices.append({"id": _account_id(row["id"]), "name": _token(row["name"]), "kind": row["kind"]})
            ids = [row["id"] for row in choices]
            effective = _account_id(data["effective_account_id"])
            if len(set(ids)) != len(ids) or effective is not None and effective not in ids:
                raise ValueError("invalid effective account")
            deliveries = []
            for raw in _items(data["deliveries"], maximum=64):
                row = _object(raw)
                if row["state"] not in {"not_requested", "pending", "applied", "failed", "unavailable"}:
                    raise ValueError("invalid delivery state")
                item = {**_projection(row), "cluster_id": _token(row["cluster_id"]), "state": row["state"],
                        "applied_at": _timestamp_text(row, "applied_at", nullable=True, request_id=request_id)}
                if (item["applied_at"] is not None) != (item["state"] == "applied"):
                    raise ValueError("applied state requires a receipt time")
                if item["state"] in {"pending", "applied", "failed"} and item["task_id"] is None:
                    raise ValueError("delivery requires a task")
                deliveries.append(item)
            if len({row["site_id"] for row in deliveries}) != len(deliveries):
                raise ValueError("duplicate site delivery")
            return cls({
                "schema_version": "account.defaults/v1", "scope": "user", "site_id": _token(site_id),
                "cluster_id": _token(data["cluster_id"]), "default_account_id": _account_id(data["default_account_id"]),
                "effective_account_id": effective, "choices": choices, "deliveries": deliveries,
            })
        except (ValueError, KeyError, TypeError) as exc:
            raise ContractError("The default account response is invalid.", request_id=request_id) from exc

    def as_dict(self) -> dict[str, Any]:
        return deepcopy(self.values)


@dataclass(frozen=True)
class DefaultAccountChange:
    values: dict[str, Any]

    @classmethod
    def from_payload(cls, payload: object, *, account_id: str | None, expected_account_id: str | None,
                     idempotency_key: str, request_id: str) -> DefaultAccountChange:
        try:
            data = _object(payload)
            expected = {"schema_version": "account.default-change/v1", "scope": "user", "state": "accepted",
                        "request_id": idempotency_key, "previous_account_id": expected_account_id,
                        "default_account_id": account_id}
            if any(data[key] != value for key, value in expected.items()):
                raise ValueError("default account acceptance mismatches intent")
            projections = [_projection(row) for row in _items(data["site_projections"], maximum=64)]
            if (len({row["site_id"] for row in projections}) != len(projections)
                    or any(row["task_id"] is None for row in projections)):
                raise ValueError("invalid accepted projection")
            return cls({**expected, "site_projections": projections})
        except (ValueError, KeyError, TypeError) as exc:
            raise ContractError("The default account acceptance is invalid.", request_id=request_id) from exc

    def as_dict(self) -> dict[str, Any]:
        return deepcopy(self.values)


def render_default_account(result: DefaultAccountState | DefaultAccountChange, *, args: Namespace | None = None) -> str:
    value = result.values
    target = value["default_account_id"]
    if isinstance(result, DefaultAccountChange):
        from .render import follow_up_command
        from .managed_runs import terminal_log
        lines = [f"默认计算账户修改请求已受理：{target or '自动选择'}（全局）", f"请求：{value['request_id']}"]
        for projection in value['site_projections']:
            command = follow_up_command(args, "account", "defaults", "--site", projection['site_id'])
            lines.append("查看站点结果：" + terminal_log(command))
        return "\n".join(lines) + "\n"
    names = {row["id"]: row["name"] for row in value["choices"]}
    lines = [f"默认计算账户：{names.get(target, target) if target else '自动选择'}（全局）",
             f"本站可选：{', '.join(row['name'] for row in value['choices']) or '暂无'}"]
    states = {"not_requested": "尚无应用记录", "pending": "等待站点应用", "applied": "已收到应用回执",
              "failed": "站点应用失败", "unavailable": "暂无法确认"}
    for row in value["deliveries"]:
        lines.append(f"{row['site_id']}：{states[row['state']]}" + (f" · {row['applied_at']}" if row["applied_at"] else ""))
    return "\n".join(lines) + "\n"
