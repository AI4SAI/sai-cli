from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from sai_cli.auth import TokenLease, TokenProvider
from sai_cli.capability import (
    CAPABILITY_HEADER,
    CapabilityProvider,
    capability_cache_key,
)
from sai_cli.client import JobQuery, PortalClient
from sai_cli.config import Settings
from sai_cli.errors import ContractError
from sai_cli.transport import JsonResponse


class FakeTransport:
    def __init__(self, payload: dict[str, Any] | None = None) -> None:
        self.payload = payload or {
            "schema_version": "sai-site-read-capability/v1",
            "capability": "opaque-capability-token",
            "expires_at": 1_700_000_300,
            "audience": "sai-site-read",
            "surface": "site-read",
            "operation": "jobs.list",
            "site_id": "site-a",
            "cluster_id": "cluster-a",
        }
        self.calls: list[dict[str, Any]] = []

    def request(
        self,
        method: str,
        path: str,
        *,
        query=None,
        headers=None,
        json_body=None,
    ) -> JsonResponse:
        self.calls.append(
            {
                "method": method,
                "path": path,
                "query": query,
                "headers": headers,
                "json_body": json_body,
            }
        )
        return JsonResponse(
            payload=dict(self.payload),
            request_id="cap-request",
            status=200,
        )


def _settings(
    tmp_path: Path,
    *,
    managed: bool = False,
    require_capability: bool = True,
) -> Settings:
    return Settings(
        base_url="https://portal.example.org",
        site_id="site-a",
        username=None if managed else "alice",
        key_id="managed-login",
        timeout_seconds=10,
        allow_insecure_http=False,
        cache_path=tmp_path / "cache" / "token-cache.json",
        use_cache=True,
        profile="default",
        managed_login_node=managed,
        require_site_capability=require_capability,
    )


def _query() -> JobQuery:
    return JobQuery(site_id="site-a", cluster_id="cluster-a")


def test_capability_cache_key_binds_origin_request_and_user_token() -> None:
    body = _query().capability_request(operation="jobs.list")
    first = capability_cache_key(
        base_url="https://portal.example.org",
        user_token="token-a",
        request_body=body,
    )
    assert first != capability_cache_key(
        base_url="https://portal.example.org",
        user_token="token-a",
        request_body={**body, "operation": "jobs.detail", "job_id": "123", "limit": None},
    )
    assert first != capability_cache_key(
        base_url="https://portal.example.org",
        user_token="token-b",
        request_body=body,
    )
    assert first == capability_cache_key(
        base_url="https://portal.example.org", user_token="token-a",
        request_body=body, read_origin=None,
    )
    gateway_a = capability_cache_key(
        base_url="https://portal.example.org", user_token="token-a",
        request_body=body, read_origin="https://gateway-a.example.org",
    )
    gateway_b = capability_cache_key(
        base_url="https://portal.example.org", user_token="token-a",
        request_body=body, read_origin="https://gateway-b.example.org",
    )
    assert len({first, gateway_a, gateway_b}) == 3


@pytest.mark.parametrize("operation", ["jobs.list", "jobs.detail"])
def test_job_capability_cache_is_isolated_by_actual_reader_origin(tmp_path: Path, operation: str) -> None:
    body = _query().capability_request(
        operation=operation, job_id="123" if operation == "jobs.detail" else None,
    )
    transport = FakeTransport()
    transport.payload["operation"] = operation
    user = TokenLease(token="user-token", expires_at=None, source="environment")
    keys = []
    for origin in ("https://gateway-a.example.org", "https://gateway-b.example.org", None):
        provider = CapabilityProvider(
            settings=replace(_settings(tmp_path), site_read_base_url=origin),
            portal_transport=transport, clock=lambda: 1_700_000_000,
        )
        first = provider.get(request_body=body, user_lease=user)
        second = provider.get(request_body=body, user_lease=user)
        assert first.source == "exchange" and second.source == "cache"
        keys.append(first.cache_key)
    assert len(set(keys)) == 3
    assert len(transport.calls) == 3
    assert all(call["json_body"] == body for call in transport.calls)


def test_billing_capability_cache_remains_bound_to_portal(tmp_path: Path) -> None:
    body = _query().capability_request(operation="billing.running-estimate")
    transport = FakeTransport()
    transport.payload["operation"] = "billing.running-estimate"
    user = TokenLease(token="user-token", expires_at=None, source="environment")
    leases = []
    for origin in (None, "https://gateway-a.example.org", "https://gateway-b.example.org"):
        provider = CapabilityProvider(
            settings=replace(_settings(tmp_path), site_read_base_url=origin),
            portal_transport=transport, clock=lambda: 1_700_000_000,
        )
        leases.append(provider.get(request_body=body, user_lease=user))
    assert [lease.source for lease in leases] == ["exchange", "cache", "cache"]
    assert len({lease.cache_key for lease in leases}) == 1
    assert len(transport.calls) == 1


def test_capability_provider_posts_exact_json_and_reuses_opaque_token(
    tmp_path: Path,
) -> None:
    transport = FakeTransport()
    settings = _settings(tmp_path)
    provider = CapabilityProvider(
        settings=settings,
        portal_transport=transport,  # type: ignore[arg-type]
        clock=lambda: 1_700_000_000,
    )
    lease = TokenLease(token="user-token", expires_at=None, source="environment")
    body = _query().capability_request(operation="jobs.list")

    first = provider.get(request_body=body, user_lease=lease)
    second = provider.get(request_body=body, user_lease=lease)

    assert first.source == "exchange"
    assert second.source == "cache"
    assert second.token == "opaque-capability-token"
    assert len(transport.calls) == 1
    call = transport.calls[0]
    assert call["method"] == "POST"
    assert call["path"] == "/v1/authz/site-read"
    assert call["headers"] == {"Authorization": "Bearer user-token"}
    assert call["json_body"] == body
    assert call["query"] is None


def test_capability_provider_rejects_mismatched_response(tmp_path: Path) -> None:
    transport = FakeTransport(
        {
            "schema_version": "sai-site-read-capability/v1",
            "capability": "opaque-capability-token",
            "expires_at": 1_700_000_300,
            "audience": "sai-site-read",
            "surface": "site-read",
            "operation": "jobs.detail",
            "site_id": "site-a",
            "cluster_id": "cluster-a",
        }
    )
    settings = _settings(tmp_path)
    provider = CapabilityProvider(
        settings=settings,
        portal_transport=transport,  # type: ignore[arg-type]
        clock=lambda: 1_700_000_000,
    )
    with pytest.raises(ContractError):
        provider.get(
            request_body=_query().capability_request(operation="jobs.list"),
            user_lease=TokenLease(
                token="user-token",
                expires_at=None,
                source="environment",
            ),
        )


def test_capability_mode_requires_cluster_before_network(tmp_path: Path) -> None:
    query = JobQuery(site_id="site-a")
    with pytest.raises(Exception, match="cluster"):
        query.capability_request(operation="jobs.list")


def test_portal_client_attaches_capability_and_bearer_to_cli_route(
    tmp_path: Path,
    job_payload: dict[str, Any],
) -> None:
    class SequencedTransport(FakeTransport):
        def request(
            self,
            method: str,
            path: str,
            *,
            query=None,
            headers=None,
            json_body=None,
        ) -> JsonResponse:
            self.calls.append(
                {
                    "method": method,
                    "path": path,
                    "query": query,
                    "headers": headers,
                    "json_body": json_body,
                }
            )
            if path == "/v1/authz/site-read":
                return JsonResponse(
                    payload=dict(self.payload),
                    request_id="cap-request",
                    status=200,
                )
            return JsonResponse(
                payload=job_payload,
                request_id="job-request",
                status=200,
            )

    transport = SequencedTransport()
    settings = _settings(tmp_path)
    user_provider = TokenProvider(
        settings=settings,
        transport=transport,  # type: ignore[arg-type]
        environ={"SAI_TOKEN": "user-token"},
    )
    capability_provider = CapabilityProvider(
        settings=settings,
        portal_transport=transport,  # type: ignore[arg-type]
        clock=lambda: 1_700_000_000,
    )
    client = PortalClient(
        transport=transport,  # type: ignore[arg-type]
        token_provider=user_provider,
        capability_provider=capability_provider,
    )

    result = client.list_jobs(_query())

    assert result.items
    assert transport.calls[-1]["path"] == "/v1/slurm/cli/jobs"
    assert transport.calls[-1]["headers"] == {
        "Authorization": "Bearer user-token",
        CAPABILITY_HEADER: "opaque-capability-token",
    }
