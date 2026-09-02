from __future__ import annotations

import hashlib
import hmac
import os
from pathlib import Path
from typing import Any

import pytest

from sai_cli.auth import TokenProvider
from sai_cli.cache import TokenCache, cache_key
from sai_cli.config import Settings
from sai_cli.errors import AuthenticationError
from sai_cli.transport import JsonResponse


class FakeTransport:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def request(self, method: str, path: str, *, query=None, headers=None) -> JsonResponse:
        self.calls.append({"method": method, "path": path, "query": query, "headers": headers})
        return JsonResponse(
            payload={"token": "issued-token", "expires_at": 1_700_000_300},
            request_id="request-token",
            status=200,
        )


def _settings(
    tmp_path: Path,
    *,
    username: str | None = "alice",
    use_cache: bool = True,
    managed: bool = False,
) -> Settings:
    return Settings(
        portal_base_url="https://portal.example.org",
        site_read_base_url="https://site-read.example.org",
        site_id="site-a",
        cluster_id="cluster-a",
        username=username,
        key_id="managed-login",
        timeout_seconds=10,
        allow_insecure_http=False,
        cache_path=tmp_path / "cache" / "token-cache.json",
        use_cache=use_cache,
        profile="default",
        managed_login_node=managed,
    )


def test_token_cache_permissions_round_trip_and_delete(tmp_path: Path) -> None:
    path = tmp_path / "cache" / "token-cache.json"
    cache = TokenCache(path)
    key = cache_key(base_url="https://example.org", username="alice", key_id="login")

    cache.put(key, token="short-token", expires_at=1_700_000_300)

    assert cache.get(key, now=1_700_000_000) == ("short-token", 1_700_000_300)
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.parent.stat().st_mode & 0o777 == 0o700
    cache.delete(key)
    assert cache.get(key, now=1_700_000_000) is None


def test_token_cache_rejects_weak_permissions(tmp_path: Path) -> None:
    path = tmp_path / "token-cache.json"
    path.write_text('{"version": 1, "entries": {}}', encoding="utf-8")
    path.chmod(0o644)

    with pytest.raises(AuthenticationError, match="permissions"):
        TokenCache(path).get("missing", now=0)


def test_token_cache_rejects_symlink(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    target.write_text('{"version": 1, "entries": {}}', encoding="utf-8")
    target.chmod(0o600)
    link = tmp_path / "token-cache.json"
    link.symlink_to(target)

    with pytest.raises(AuthenticationError, match="regular file"):
        TokenCache(link).get("missing", now=0)


def test_hmac_exchange_uses_contract_and_reuses_cache(tmp_path: Path) -> None:
    transport = FakeTransport()
    settings = _settings(tmp_path)
    provider = TokenProvider(
        settings=settings,
        transport=transport,  # type: ignore[arg-type]
        environ={"SAI_API_SHARED_SECRET": "managed-secret"},
        clock=lambda: 1_700_000_000,
        nonce_factory=lambda: "fixed-nonce",
    )

    first = provider.get()
    second = provider.get()

    canonical = "alice\n1700000000\nfixed-nonce\nmanaged-login"
    expected = hmac.new(b"managed-secret", canonical.encode(), hashlib.sha256).hexdigest()
    assert first.token == "issued-token"
    assert first.source == "exchange"
    assert second.token == "issued-token"
    assert second.source == "cache"
    assert len(transport.calls) == 1
    assert transport.calls[0]["query"]["sig"] == expected
    assert transport.calls[0]["query"]["nonce"] == "fixed-nonce"
    assert "managed-secret" not in str(transport.calls[0])


def test_environment_token_does_not_require_username_or_touch_cache(tmp_path: Path) -> None:
    transport = FakeTransport()
    settings = _settings(tmp_path, username=None)
    provider = TokenProvider(
        settings=settings,
        transport=transport,  # type: ignore[arg-type]
        environ={"SAI_TOKEN": "direct-token"},
    )

    lease = provider.get()

    assert lease.source == "environment"
    assert lease.token == "direct-token"
    assert not settings.cache_path.exists()
    assert transport.calls == []


def test_missing_credentials_fails_without_network(tmp_path: Path) -> None:
    transport = FakeTransport()
    provider = TokenProvider(
        settings=_settings(tmp_path),
        transport=transport,  # type: ignore[arg-type]
        environ={},
    )

    with pytest.raises(AuthenticationError, match="no Bearer token"):
        provider.get()
    assert transport.calls == []


def test_managed_login_node_never_uses_hmac_exchange(tmp_path: Path) -> None:
    transport = FakeTransport()
    provider = TokenProvider(
        settings=_settings(tmp_path, username=None, managed=True),
        transport=transport,  # type: ignore[arg-type]
        environ={"SAI_API_SHARED_SECRET": "global-secret"},
    )

    with pytest.raises(AuthenticationError, match="short-lived SAI_TOKEN"):
        provider.get()
    assert transport.calls == []
