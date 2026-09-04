from __future__ import annotations

import pytest

from sai_cli.errors import ConfigError, ContractError
from sai_cli.oidc import OidcClient, OidcPending
from sai_cli.transport import JsonResponse


class _Transport:
    base_url = "https://identity.example.org"

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _metadata() -> dict[str, str]:
    return {
        "issuer": "https://identity.example.org",
        "device_authorization_endpoint": "https://identity.example.org/oauth/device",
        "token_endpoint": "https://identity.example.org/oauth/token",
        "revocation_endpoint": "https://identity.example.org/oauth/revoke",
        "userinfo_endpoint": "https://identity.example.org/userinfo",
    }


def _client(transport: _Transport) -> OidcClient:
    return OidcClient(
        transport=transport,  # type: ignore[arg-type]
        issuer_url=transport.base_url,
        client_id="sai-cli",
        scope="openid offline_access sai.compute.read",
        resource="https://portal.example.org",
    )


def test_device_flow_uses_discovery_and_form_contract() -> None:
    transport = _Transport(
        [
            JsonResponse(_metadata(), "discovery", 200),
            JsonResponse(
                {
                    "device_code": "opaque-device-code",
                    "user_code": "ABCD-EFGH",
                    "verification_uri": "https://identity.example.org/activate",
                    "expires_in": 300,
                    "interval": 5,
                },
                "device",
                200,
            ),
            JsonResponse(
                {
                    "token_type": "Bearer",
                    "access_token": "opaque-access",
                    "expires_in": 900,
                    "refresh_token": "opaque-refresh",
                    "refresh_expires_in": 86400,
                },
                "token",
                200,
            ),
        ]
    )
    client = _client(transport)
    auth = client.start_device_authorization(now=1_700_000_000)
    assert auth.user_code == "ABCD-EFGH"
    assert auth.expires_at == 1_700_000_300
    result = client.poll_device_token(device_code=auth.device_code, now=1_700_000_000)
    assert result is not None
    assert result.access_token == "opaque-access"
    assert transport.calls[1][2]["form_body"] == {
        "client_id": "sai-cli",
        "scope": "openid offline_access sai.compute.read",
        "resource": "https://portal.example.org",
    }
    assert transport.calls[2][2]["form_body"]["grant_type"] == "urn:ietf:params:oauth:grant-type:device_code"


def test_pending_device_poll_is_not_a_terminal_auth_error() -> None:
    pending = ConfigError("pending", code="authorization_pending")
    transport = _Transport([JsonResponse(_metadata(), "discovery", 200), pending])
    client = _client(transport)
    with pytest.raises(OidcPending):
        client.poll_device_token(device_code="opaque-device-code", now=1_700_000_000)


def test_discovery_rejects_cross_origin_endpoint() -> None:
    metadata = _metadata()
    metadata["token_endpoint"] = "https://evil.example.org/oauth/token"
    transport = _Transport([JsonResponse(metadata, "discovery", 200)])
    with pytest.raises(ContractError, match="trusted HTTPS endpoint"):
        _client(transport).discover()


def test_oidc_client_requires_offline_access() -> None:
    transport = _Transport([])
    with pytest.raises(ConfigError, match="offline_access"):
        OidcClient(
            transport=transport,  # type: ignore[arg-type]
            issuer_url=transport.base_url,
            client_id="sai-cli",
            scope="openid",
        )
