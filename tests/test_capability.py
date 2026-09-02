from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from sai_cli.auth import TokenLease, TokenProvider
from sai_cli.capability import (
    CAPABILITY_HEADER,
    CapabilityProvider,
    capability_cache_key,
)
from sai_cli.client import JobQuery, SaiClient
from sai_cli.config import Settings
from sai_cli.errors import AuthenticationError, ContractError, ForbiddenError
from sai_cli.transport import JsonResponse


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        portal_base_url="https://portal.example.org",
        site_read_base_url="https://site-read.example.org",
        site_id="site-a",
        cluster_id="cluster-a",
        username="alice",
        key_id="managed-login",
        timeout_seconds=10,
        allow_insecure_http=False,
        cache_path=tmp_path / "cache" / "token-cache.json",
        use_cache=True,
        profile="default",
    )


def _request(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "operation": "jobs.list",
        "site_id": "site-a",
        "cluster_id": "cluster-a",
        "scope_type": "self",
        "slurm_account_id": None,
        "slurm_account_name": None,
        "partition": None,
        "states": ["R"],
        "job_id": None,
        "limit": 1,
    }
    value.update(overrides)
    return value


def _capability_payload(**overrides: object) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema_version": "sai-site-read-capability/v1",
        "capability": "opaque-capability-token",
        "expires_at": 1_700_000_120,
        "audience": "sai-site-read",
        "surface": "site-read",
        "operation": "jobs.list",
        "site_id": "site-a",
        "cluster_id": "cluster-a",
    }
    value.update(overrides)
    return value


class FakeTransport:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
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
            request_id="fake-request",
            status=200,
        )


def test_capability_cache_key_binds_both_origins_request_and_user_token() -> None:
    first = capability_cache_key(
        portal_base_url="https://portal.example.org",
        site_read_base_url="https://site-read.example.org",
        user_token="token-a",
        request_body=_request(),
    )

    assert first != capability_cache_key(
        portal_base_url="https://other-portal.example.org",
        site_read_base_url="https://site-read.example.org",
        user_token="token-a",
        request_body=_request(),
    )
    assert first != capability_cache_key(
        portal_base_url="https://portal.example.org",
        site_read_base_url="https://other-read.example.org",
        user_token="token-a",
        request_body=_request(),
    )
    assert first != capability_cache_key(
        portal_base_url="https://portal.example.org",
        site_read_base_url="https://site-read.example.org",
        user_token="token-b",
        request_body=_request(),
    )
    assert first != capability_cache_key(
        portal_base_url="https://portal.example.org",
        site_read_base_url="https://site-read.example.org",
        user_token="token-a",
        request_body=_request(states=["PD"]),
    )


def test_capability_provider_posts_and_reuses_opaque_token(tmp_path: Path) -> None:
    transport = FakeTransport(_capability_payload())
    provider = CapabilityProvider(
        settings=_settings(tmp_path),
        portal_transport=transport,  # type: ignore[arg-type]
        clock=lambda: 1_700_000_000,
    )
    user_lease = TokenLease(
        token="user-token",
        expires_at=None,
        source="environment",
    )

    first = provider.get(request_body=_request(), user_lease=user_lease)
    second = provider.get(request_body=_request(), user_lease=user_lease)

    assert first.source == "exchange"
    assert second.source == "cache"
    assert second.token == "opaque-capability-token"
    assert len(transport.calls) == 1
    assert transport.calls[0] == {
        "method": "POST",
        "path": "/v1/authz/site-read",
        "query": None,
        "headers": {"Authorization": "Bearer user-token"},
        "json_body": _request(),
    }


@pytest.mark.parametrize(
    "payload",
    [
        _capability_payload(operation="jobs.detail"),
        _capability_payload(audience="sai-pilot"),
        _capability_payload(surface="agent-session"),
        _capability_payload(site_id="site-b"),
        _capability_payload(cluster_id="cluster-b"),
        _capability_payload(expires_at=1_700_000_301),
    ],
)
def test_capability_provider_rejects_mismatched_response(
    tmp_path: Path,
    payload: dict[str, Any],
) -> None:
    provider = CapabilityProvider(
        settings=_settings(tmp_path),
        portal_transport=FakeTransport(payload),  # type: ignore[arg-type]
        clock=lambda: 1_700_000_000,
    )

    with pytest.raises(ContractError):
        provider.get(
            request_body=_request(),
            user_lease=TokenLease(
                token="user-token",
                expires_at=None,
                source="environment",
            ),
        )


def test_dual_origin_client_never_sends_portal_bearer_to_gateway(
    tmp_path: Path,
    job_payload: dict[str, Any],
) -> None:
    portal = FakeTransport(_capability_payload())
    gateway = FakeTransport(job_payload)
    settings = _settings(tmp_path)
    token_provider = TokenProvider(
        settings=settings,
        transport=portal,  # type: ignore[arg-type]
        environ={"SAI_TOKEN": "user-token"},
    )
    client = SaiClient(
        portal_transport=portal,  # type: ignore[arg-type]
        site_read_transport=gateway,  # type: ignore[arg-type]
        token_provider=token_provider,
        capability_provider=CapabilityProvider(
            settings=settings,
            portal_transport=portal,  # type: ignore[arg-type]
            clock=lambda: 1_700_000_000,
        ),
    )

    result = client.list_jobs(JobQuery(site_id="site-a", cluster_id="cluster-a"))

    assert result.items
    assert portal.calls[0]["headers"] == {"Authorization": "Bearer user-token"}
    assert gateway.calls == [
        {
            "method": "GET",
            "path": "/v1/site-read/jobs",
            "query": None,
            "headers": {CAPABILITY_HEADER: "opaque-capability-token"},
            "json_body": None,
        }
    ]


class AuthenticationSequenceTransport(FakeTransport):
    def __init__(self, payload: dict[str, Any], failures: int) -> None:
        super().__init__(payload)
        self.failures = failures

    def request(self, *args, **kwargs) -> JsonResponse:  # noqa: ANN002, ANN003
        self.calls.append(
            {
                "method": args[0],
                "path": args[1],
                "query": kwargs.get("query"),
                "headers": kwargs.get("headers"),
                "json_body": kwargs.get("json_body"),
            }
        )
        if self.failures:
            self.failures -= 1
            raise AuthenticationError("expired", code="capability_expired")
        return JsonResponse(
            payload=dict(self.payload),
            request_id="gateway-request",
            status=200,
        )


def _client_with_gateway(
    tmp_path: Path,
    *,
    job_payload: dict[str, Any],
    failures: int,
) -> tuple[SaiClient, FakeTransport, AuthenticationSequenceTransport]:
    portal = FakeTransport(_capability_payload())
    gateway = AuthenticationSequenceTransport(job_payload, failures)
    settings = _settings(tmp_path)
    token_provider = TokenProvider(
        settings=settings,
        transport=portal,  # type: ignore[arg-type]
        environ={"SAI_TOKEN": "user-token"},
    )
    return (
        SaiClient(
            portal_transport=portal,  # type: ignore[arg-type]
            site_read_transport=gateway,  # type: ignore[arg-type]
            token_provider=token_provider,
            capability_provider=CapabilityProvider(
                settings=settings,
                portal_transport=portal,  # type: ignore[arg-type]
                clock=lambda: 1_700_000_000,
            ),
        ),
        portal,
        gateway,
    )


def test_authentication_refresh_has_one_command_level_retry(
    tmp_path: Path,
    job_payload: dict[str, Any],
) -> None:
    client, portal, gateway = _client_with_gateway(
        tmp_path,
        job_payload=job_payload,
        failures=1,
    )

    assert client.list_jobs(
        JobQuery(site_id="site-a", cluster_id="cluster-a")
    ).items
    assert len(portal.calls) == 2
    assert len(gateway.calls) == 2
    assert all("Authorization" not in call["headers"] for call in gateway.calls)


def test_second_authentication_failure_is_not_retried(
    tmp_path: Path,
    job_payload: dict[str, Any],
) -> None:
    client, portal, gateway = _client_with_gateway(
        tmp_path,
        job_payload=job_payload,
        failures=2,
    )

    with pytest.raises(AuthenticationError):
        client.list_jobs(JobQuery(site_id="site-a", cluster_id="cluster-a"))
    assert len(portal.calls) == 2
    assert len(gateway.calls) == 2


def test_forbidden_gateway_response_is_not_retried(
    tmp_path: Path,
    job_payload: dict[str, Any],
) -> None:
    class ForbiddenTransport(AuthenticationSequenceTransport):
        def request(self, *args, **kwargs) -> JsonResponse:  # noqa: ANN002, ANN003
            raise ForbiddenError("denied")

    client, portal, _gateway = _client_with_gateway(
        tmp_path,
        job_payload=job_payload,
        failures=0,
    )
    forbidden = ForbiddenTransport(job_payload, 0)
    client.site_read_transport = forbidden  # type: ignore[assignment]

    with pytest.raises(ForbiddenError):
        client.list_jobs(JobQuery(site_id="site-a", cluster_id="cluster-a"))
    assert len(portal.calls) == 1
