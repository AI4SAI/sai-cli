from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from sai_cli.auth import DeviceTokenResult, TokenProvider
from sai_cli.cache import TokenCache, device_access_cache_key, device_refresh_cache_key
from sai_cli.config import Settings
from sai_cli.errors import AuthenticationError, NetworkError


class FakeTransport:
    def request(self, *_args, **_kwargs):
        raise AssertionError("credential selection must not request a Portal token")


def _settings(
    tmp_path: Path,
    *,
    use_cache: bool = True,
    managed: bool = False,
) -> Settings:
    return Settings(
        base_url="https://portal.example.org",
        site_id="site-a",
        timeout_seconds=10,
        allow_insecure_http=False,
        cache_path=tmp_path / "cache" / "token-cache.json",
        use_cache=use_cache,
        profile="default",
        managed_login_node=managed,
        require_site_capability=managed,
    )


def test_token_cache_permissions_round_trip_and_delete(tmp_path: Path) -> None:
    path = tmp_path / "cache" / "token-cache.json"
    cache = TokenCache(path)
    key = device_access_cache_key(base_url="https://example.org")

    cache.put(key, token="short-token", expires_at=1_700_000_300)

    assert cache.get(key, now=1_700_000_000) == ("short-token", 1_700_000_300)
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.parent.stat().st_mode & 0o777 == 0o700
    cache.delete(key)
    assert cache.get(key, now=1_700_000_000) is None


def test_device_cache_keys_bind_identity_and_portal_context() -> None:
    common = {
        "base_url": "https://portal.example.org",
        "identity_issuer": "https://id.example.org",
        "client_id": "sai-cli",
        "resource": "https://portal.example.org",
        "scope": "openid offline_access sai.compute.read",
    }
    first = device_access_cache_key(**common)
    assert first != device_access_cache_key(**{**common, "resource": "https://other.example.org"})
    assert first != device_access_cache_key(**{**common, "client_id": "other-client"})
    assert first != device_access_cache_key(**{**common, "scope": "openid offline_access"})


def test_token_cache_rejects_weak_permissions(tmp_path: Path) -> None:
    path = tmp_path / "token-cache.json"
    path.write_text('{"version": 1, "entries": {}}', encoding="utf-8")
    path.chmod(0o644)

    with pytest.raises(AuthenticationError, match="permissions"):
        TokenCache(path).get("missing", now=0)
    with pytest.raises(AuthenticationError, match="permissions"):
        TokenCache(path).scope("missing")


def test_token_cache_rejects_whitespace_credentials(tmp_path: Path) -> None:
    path = tmp_path / "cache" / "token-cache.json"
    with pytest.raises(AuthenticationError, match="entry is invalid"):
        TokenCache(path).put("key", token="token with-space", expires_at=1_700_000_300)


def test_token_cache_rejects_symlink(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    target.write_text('{"version": 1, "entries": {}}', encoding="utf-8")
    target.chmod(0o600)
    link = tmp_path / "token-cache.json"
    link.symlink_to(target)

    with pytest.raises(AuthenticationError, match="regular file"):
        TokenCache(link).get("missing", now=0)
    with pytest.raises(AuthenticationError, match="regular file"):
        TokenCache(link).scope("missing")


def test_token_cache_delete_rejects_dangling_symlink(tmp_path: Path) -> None:
    link = tmp_path / "token-cache.json"
    link.symlink_to(tmp_path / "missing.json")

    with pytest.raises(AuthenticationError, match="regular file"):
        TokenCache(link).delete("key")


def test_token_cache_rejects_symlink_parent(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "cache"
    link.symlink_to(target, target_is_directory=True)

    with pytest.raises(AuthenticationError, match="directory"):
        TokenCache(link / "token-cache.json").put(
            "key",
            token="short-token",
            expires_at=1_700_000_300,
        )


def test_token_cache_put_prunes_expired_entries_with_provider_clock(tmp_path: Path) -> None:
    path = tmp_path / "cache" / "token-cache.json"
    cache = TokenCache(path, clock=lambda: 100)
    cache.put("expired", token="old", expires_at=100)
    cache.put("live", token="new", expires_at=200)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert set(payload["entries"]) == {"live"}


def test_environment_token_stays_process_local(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    provider = TokenProvider(
        settings=settings,
        transport=FakeTransport(),  # type: ignore[arg-type]
        environ={"SAI_TOKEN": "direct-token"},
    )

    lease = provider.get()

    assert lease.source == "environment"
    assert lease.token == "direct-token"
    assert not settings.cache_path.exists()
    assert not provider.credential_cache.path.exists()


@pytest.mark.parametrize("managed", [False, True])
def test_missing_credentials_requires_identity_login(tmp_path: Path, managed: bool) -> None:
    provider = TokenProvider(
        settings=_settings(tmp_path, managed=managed),
        transport=FakeTransport(),  # type: ignore[arg-type]
        environ={},
    )

    with pytest.raises(AuthenticationError, match="sai auth login") as error:
        provider.get()
    assert error.value.code == "credentials_unavailable"


@pytest.mark.parametrize("managed", [False, True])
def test_legacy_cached_bearer_cannot_authenticate(tmp_path: Path, managed: bool) -> None:
    settings = _settings(tmp_path, managed=managed)
    legacy_key = hashlib.sha256(
        "\0".join((settings.base_url, "alice", "managed-login")).encode()
    ).hexdigest()
    provider = TokenProvider(settings=settings, transport=FakeTransport(), environ={},
                             clock=lambda: 1_700_000_000)
    provider.cache.put(legacy_key, token="old-portal-bearer", expires_at=1_700_000_300)
    original_cache = settings.cache_path.read_bytes()

    with pytest.raises(AuthenticationError, match="sai auth login"):
        provider.get()
    assert settings.cache_path.read_bytes() == original_cache


@pytest.mark.parametrize("refresh_expiry", [None, 1_700_100_000])
def test_device_refresh_rotates_and_reuses_protected_cache(
    tmp_path: Path, refresh_expiry: int | None,
) -> None:
    class FakeOidc:
        issuer_url = "https://portal.example.org"
        client_id = "sai-cli"
        scope = "openid offline_access"
        resource = None

        calls = 0

        def refresh(self, *, refresh_token: str, now: int) -> DeviceTokenResult:
            self.calls += 1
            assert refresh_token == "refresh-old"
            return DeviceTokenResult(
                access_token="access-new",  # public-scan: allow-test-vector
                access_expires_at=now + 300,
                refresh_token="refresh-new",  # public-scan: allow-test-vector
                refresh_expires_at=refresh_expiry,
                subject="subject-1",
                device_id="device-1",
            )

    settings = _settings(tmp_path, managed=True)
    oidc = FakeOidc()
    provider = TokenProvider(
        settings=settings,
        transport=FakeTransport(),  # type: ignore[arg-type]
        environ={},
        clock=lambda: 1_700_000_000,
        oidc_client=oidc,  # type: ignore[arg-type]
    )
    provider.credential_cache.put(
        device_refresh_cache_key(
            base_url=settings.base_url,
            identity_issuer=settings.base_url,
            client_id=settings.oidc_client_id,
            scope=settings.oidc_scope,
        ),
        token="refresh-old",
        expires_at=refresh_expiry,
        allow_unknown_expiry=True,
    )
    provider.store_pending_device_code(device_code="pending-code", expires_at=1_700_000_300)

    lease = provider.get()
    assert lease.token == "access-new"
    assert lease.source == "cache"
    assert provider.device_refresh(now=1_700_000_000) == ("refresh-new", refresh_expiry)
    assert provider.device_scope() is None  # Legacy grant scope remains unknown on omission.
    assert oidc.calls == 1


def test_unknown_expiry_is_not_allowed_for_access_or_pending_tokens(tmp_path: Path) -> None:
    cache = TokenCache(tmp_path / "cache" / "tokens.json")
    with pytest.raises(AuthenticationError, match="entry is invalid"):
        cache.put("key", token="opaque-refresh", expires_at=None)
    cache.put("key", token="opaque-refresh", expires_at=None, allow_unknown_expiry=True)
    with pytest.raises(AuthenticationError, match="entry is invalid"):
        cache.get("key", now=1_700_000_000)
    assert cache.get("key", now=1_800_000_000, allow_unknown_expiry=True) == ("opaque-refresh", None)


def test_install_device_tokens_requires_persistent_cache(tmp_path: Path) -> None:
    settings = _settings(tmp_path, managed=True, use_cache=False)
    provider = TokenProvider(
        settings=settings,
        transport=FakeTransport(),  # type: ignore[arg-type]
        environ={},
        clock=lambda: 1_700_000_000,
    )
    result = DeviceTokenResult(
        access_token="access",  # public-scan: allow-test-vector
        access_expires_at=1_700_000_300,
        refresh_token="refresh",  # public-scan: allow-test-vector
        refresh_expires_at=1_700_100_000,
        subject="subject-1",
        device_id="device-1",
    )
    with pytest.raises(AuthenticationError, match="credential cache"):
        provider.install_device_tokens(result)


def test_logout_clears_local_device_credentials_when_identity_is_unreachable(tmp_path: Path) -> None:
    class UnreachableOidc:
        issuer_url = "https://portal.example.org"
        client_id = "sai-cli"
        scope = "openid offline_access"
        resource = None

        def revoke(self, *, refresh_token: str) -> bool:
            raise NetworkError()

    settings = _settings(tmp_path, managed=True)
    provider = TokenProvider(
        settings=settings,
        transport=FakeTransport(),  # type: ignore[arg-type]
        environ={},
        clock=lambda: 1_700_000_000,
        oidc_client=UnreachableOidc(),  # type: ignore[arg-type]
    )
    provider.install_device_tokens(
        DeviceTokenResult(
            access_token="access",  # public-scan: allow-test-vector
            access_expires_at=1_700_000_300,
            refresh_token="refresh",  # public-scan: allow-test-vector
            refresh_expires_at=1_700_100_000,
        )
    )

    assert provider.revoke_device() is False
    assert provider.device_refresh(now=1_700_000_000) is None
