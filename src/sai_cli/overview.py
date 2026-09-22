"""Allowlisted account overview. All financial and inbox facts are server-owned."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import re
from typing import Any
from urllib.parse import quote, urljoin

from .catalog import _boolean, _count, _items, _object, _text, _token
from .contracts import _timestamp_text
from .errors import ConfigError, ContractError
from .storage_summary import clean_workspace_key


_AMOUNT = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?")


def _choice(value: object, choices: set[str]) -> str:
    if not isinstance(value, str) or value not in choices:
        raise ValueError("invalid overview state")
    return value


def _nullable(value: object) -> str | None:
    return None if value is None else _text(value, maximum=256)


def _amount(value: object) -> str | None:
    if value is None:
        return None
    text = _text(value, maximum=64)
    if _AMOUNT.fullmatch(text) is None:
        raise ValueError("invalid amount")
    return text


@dataclass(frozen=True)
class AccountOverview:
    values: dict[str, Any]

    @classmethod
    def from_payload(cls, payload: object, *, site_id: str, account: str | None = None, request_id: str) -> AccountOverview:
        try:
            data = _object(payload)
            if data["schema_version"] != "account.overview/v1" or data["site_id"] != site_id:
                raise ValueError("overview scope mismatch")
            context = _object(data["context"])
            result = {
                "schema_version": "account.overview/v1", "site_id": _token(site_id),
                "observed_at": _timestamp_text(data, "observed_at", nullable=False, request_id=request_id),
                "user_name": _token(data["user_name"]),
                "context": {"state": _choice(context["state"], {"available", "unavailable"}),
                            **{key: _nullable(context[key]) for key in
                               ("workspace_key", "kind", "label", "slurm_account", "canonical_account", "default_account")}},
                "funds": None, "inbox": None,
            }
            if context["state"] == "available":
                if context["kind"] not in {"personal", "org", "project"}:
                    raise ValueError("invalid identity kind")
                for key in ("workspace_key", "label", "slurm_account"):
                    _text(context[key], maximum=256)
                clean_workspace_key(context["workspace_key"])
                if not context["workspace_key"].startswith(context["kind"] + ":"):
                    raise ValueError("workspace kind mismatch")
                if account is not None and account not in {context["slurm_account"], context["canonical_account"]}:
                    raise ValueError("overview account mismatch")
            elif data["funds"] is not None or data["inbox"] is not None:
                raise ValueError("unresolved identity cannot carry private facts")
            access = _object(data["access"])
            result["access"] = {
                "state": _choice(access["state"], {"normal", "restricted", "restriction_pending", "recovery_pending", "failed"}),
                "verification_current": _boolean(access["verification_current"]),
                "initial_verification_deadline": _timestamp_text(access, "initial_verification_deadline", nullable=True, request_id=request_id),
                "submit_allowed": None if access["submit_allowed"] is None else _boolean(access["submit_allowed"]),
            }
            if data["funds"] is not None:
                funds = _object(data["funds"])
                if funds["currency"] != "CNY":
                    raise ValueError("invalid currency")
                parsed = {"state": _choice(funds["state"], {"available", "not_authorized", "unavailable"}),
                          "currency": "CNY", **{key: _amount(funds[key]) for key in
                          ("net_balance", "available_credit", "postpaid_available", "running_cash_exposure", "budget_available")},
                          "budget_mode": None if funds["budget_mode"] is None else _choice(funds["budget_mode"], {"limited", "unlimited"}),
                          "credit_expires_at": _timestamp_text(funds, "credit_expires_at", nullable=True, request_id=request_id)}
                if parsed["state"] != "available" and any(v is not None for k, v in parsed.items() if k not in {"state", "currency"}):
                    raise ValueError("unavailable funds cannot carry amounts")
                if parsed["budget_mode"] == "limited" and parsed["budget_available"] is None:
                    raise ValueError("limited budget amount is missing")
                result["funds"] = parsed
            if data["inbox"] is not None:
                inbox = _object(data["inbox"])
                count = _count(inbox["unread_count"])
                items = _items(inbox["items"], maximum=2)
                if count is None or count < len(items):
                    raise ValueError("invalid unread count")
                result["inbox"] = {"state": _choice(inbox["state"], {"available"}), "unread_count": count, "items": [
                    {"message_id": _token(item["message_id"]), "title": _text(item["title"], maximum=180),
                     "created_at": _timestamp_text(item, "created_at", nullable=False, request_id=request_id)}
                    for item in map(_object, items)]}
            return cls(result)
        except (ValueError, KeyError, TypeError, ConfigError) as exc:
            raise ContractError("The account overview is invalid.", request_id=request_id) from exc

    def as_dict(self) -> dict[str, Any]:
        return deepcopy(self.values)

    def messages_url(self, base_url: str) -> str:
        workspace = self.values["context"]["workspace_key"]
        route = "messages" if workspace is None else f"workspaces/{quote(workspace, safe='')}/{quote(self.values['site_id'], safe='')}/messages"
        return urljoin(base_url, "/portal/#/portal/" + route)
