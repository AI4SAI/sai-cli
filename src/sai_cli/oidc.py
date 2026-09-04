"""Small OAuth/OIDC client for the SAI Identity device flow.

Protocol mechanics stay on the Identity provider (and its maintained OIDC
engine).  This module only discovers the provider metadata, sends the
standard Device Authorization Grant requests, validates bounded responses, and
returns opaque tokens to the credential layer.
"""

from __future__ import annotations

from dataclasses import dataclass
import ipaddress
from typing import Mapping
from urllib.parse import urlsplit

from .errors import AuthenticationError, ConfigError, ContractError, SaiCliError
from .transport import JsonResponse, JsonTransport


DEVICE_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:device_code"


@dataclass(frozen=True)
class OidcMetadata:
    issuer: str
    device_authorization_endpoint: str
    token_endpoint: str
    revocation_endpoint: str | None


@dataclass(frozen=True)
class DeviceAuthorization:
    device_code: str
    user_code: str
    verification_url: str
    expires_at: int
    interval_seconds: int


@dataclass(frozen=True)
class DeviceTokenResult:
    access_token: str
    access_expires_at: int
    refresh_token: str
    refresh_expires_at: int
    subject: str | None = None
    device_id: str | None = None


class OidcPending(Exception):
    """The user has not approved the device yet."""


class OidcSlowDown(Exception):
    """The provider asked the client to poll less frequently."""


def _token(value: object, *, field: str) -> str:
    if not isinstance(value, str):
        raise ContractError(f"the Identity {field} is invalid")
    value = value.strip()
    if not value or len(value) > 16_384 or any(ord(char) < 33 or ord(char) == 127 for char in value):
        raise ContractError(f"the Identity {field} is invalid")
    return value


def _text(value: object, *, field: str, maximum: int = 512) -> str:
    if not isinstance(value, str):
        raise ContractError(f"the Identity {field} is invalid")
    value = value.strip()
    if not value or len(value) > maximum or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ContractError(f"the Identity {field} is invalid")
    return value


def _positive_int(value: object, *, field: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ContractError(f"the Identity {field} is invalid")
    return value


def _same_origin(left: str, right: str) -> bool:
    try:
        a = urlsplit(left)
        b = urlsplit(right)
    except ValueError:
        return False
    try:
        a_port = a.port or (443 if a.scheme == "https" else 80)
        b_port = b.port or (443 if b.scheme == "https" else 80)
    except ValueError:
        return False
    return (
        a.scheme.lower() == b.scheme.lower()
        and (a.hostname or "").lower().rstrip(".") == (b.hostname or "").lower().rstrip(".")
        and a_port == b_port
    )


def _trusted_scheme(url: str) -> bool:
    try:
        parsed = urlsplit(url)
    except ValueError:
        return False
    if parsed.scheme == "https":
        return True
    if parsed.scheme != "http" or not parsed.hostname:
        return False
    host = parsed.hostname.rstrip(".").lower()
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class OidcClient:
    def __init__(
        self,
        *,
        transport: JsonTransport,
        issuer_url: str,
        client_id: str,
        scope: str,
        resource: str | None = None,
    ) -> None:
        self.transport = transport
        try:
            parsed_issuer = urlsplit(issuer_url)
        except ValueError as exc:
            raise ConfigError("the Identity issuer is invalid") from exc
        issuer = issuer_url.strip().rstrip("/")
        if (
            not _trusted_scheme(issuer)
            or not parsed_issuer.hostname
            or parsed_issuer.username
            or parsed_issuer.password
            or parsed_issuer.query
            or parsed_issuer.fragment
            or not _same_origin(issuer, transport.base_url)
        ):
            raise ConfigError("the Identity issuer is invalid")
        self.issuer_url = issuer
        self.client_id = _text(client_id, field="client_id", maximum=128)
        self.scope = _text(scope, field="scope", maximum=1024)
        if "offline_access" not in self.scope.split():
            raise ConfigError("the Identity scope must include offline_access")
        self.resource = resource.strip() if isinstance(resource, str) and resource.strip() else None
        self._metadata: OidcMetadata | None = None

    def discover(self, *, force: bool = False) -> OidcMetadata:
        if self._metadata is not None and not force:
            return self._metadata
        response = self.transport.request(
            "GET",
            self._relative_path(
                f"{urlsplit(self.issuer_url).path.rstrip('/')}/.well-known/openid-configuration"
            ),
        )
        payload = response.payload
        issuer = self._endpoint(
            payload.get("issuer"),
            field="issuer",
            request_id=response.request_id,
        )
        if issuer.rstrip("/") != self.issuer_url:
            raise ContractError(
                "the Identity discovery issuer does not match configuration",
                request_id=response.request_id,
            )
        device = self._endpoint(
            payload.get("device_authorization_endpoint"),
            field="device_authorization_endpoint",
            request_id=response.request_id,
        )
        token = self._endpoint(
            payload.get("token_endpoint"),
            field="token_endpoint",
            request_id=response.request_id,
        )
        revocation = payload.get("revocation_endpoint")
        revocation_url = (
            self._endpoint(revocation, field="revocation_endpoint", request_id=response.request_id)
            if revocation is not None
            else None
        )
        self._metadata = OidcMetadata(
            issuer=issuer,
            device_authorization_endpoint=device,
            token_endpoint=token,
            revocation_endpoint=revocation_url,
        )
        return self._metadata

    def start_device_authorization(self, *, now: int) -> DeviceAuthorization:
        metadata = self.discover()
        form: dict[str, str | int] = {
            "client_id": self.client_id,
            "scope": self.scope,
        }
        if self.resource:
            form["resource"] = self.resource
        response = self._request(metadata.device_authorization_endpoint, form=form)
        payload = response.payload
        device_code = _token(payload.get("device_code"), field="device_code")
        user_code = _text(payload.get("user_code"), field="user_code", maximum=128)
        complete = payload.get("verification_uri_complete")
        plain = payload.get("verification_uri")
        verification_url = complete if complete is not None else plain
        verification_url = _text(verification_url, field="verification_uri", maximum=2048)
        self._validate_browser_url(verification_url, request_id=response.request_id)
        expires_in = _positive_int(
            payload.get("expires_in"),
            field="expires_in",
            minimum=30,
            maximum=1800,
        )
        interval_raw = payload.get("interval", 5)
        interval = _positive_int(
            interval_raw,
            field="interval",
            minimum=1,
            maximum=30,
        )
        return DeviceAuthorization(
            device_code=device_code,
            user_code=user_code,
            verification_url=verification_url,
            expires_at=now + expires_in,
            interval_seconds=interval,
        )

    def poll_device_token(self, *, device_code: str, now: int) -> DeviceTokenResult | None:
        metadata = self.discover()
        form: dict[str, str | int] = {
            "grant_type": DEVICE_GRANT_TYPE,
            "device_code": _token(device_code, field="device_code"),
            "client_id": self.client_id,
        }
        if self.resource:
            form["resource"] = self.resource
        try:
            response = self._request(metadata.token_endpoint, form=form)
        except SaiCliError as exc:
            if exc.code == "authorization_pending":
                raise OidcPending from exc
            if exc.code == "slow_down":
                raise OidcSlowDown from exc
            if exc.code in {"expired_token", "access_denied", "invalid_grant"}:
                raise AuthenticationError(
                    "Identity device authorization is no longer valid; start login again",
                    code="credentials_unavailable",
                    request_id=exc.request_id,
                ) from exc
            raise
        return self._parse_token_response(response.payload, now=now, request_id=response.request_id)

    def refresh(self, *, refresh_token: str, now: int) -> DeviceTokenResult:
        metadata = self.discover()
        form: dict[str, str | int] = {
            "grant_type": "refresh_token",
            "refresh_token": _token(refresh_token, field="refresh_token"),
            "client_id": self.client_id,
        }
        if self.resource:
            form["resource"] = self.resource
        try:
            response = self._request(metadata.token_endpoint, form=form)
        except SaiCliError as exc:
            if exc.code in {"invalid_grant", "invalid_token", "unauthorized_client"}:
                raise AuthenticationError(
                    "the Identity device session is no longer valid; run `sai auth login`",
                    code="credentials_unavailable",
                    request_id=exc.request_id,
                ) from exc
            raise
        return self._parse_token_response(response.payload, now=now, request_id=response.request_id)

    def revoke(self, *, refresh_token: str) -> bool:
        metadata = self.discover()
        if not metadata.revocation_endpoint:
            return False
        form: dict[str, str | int] = {
            "token": _token(refresh_token, field="refresh_token"),
            "token_type_hint": "refresh_token",
            "client_id": self.client_id,
        }
        try:
            self._request(
                metadata.revocation_endpoint,
                form=form,
                allow_empty_response=True,
            )
        except SaiCliError as exc:
            if exc.code in {"invalid_token", "invalid_grant"}:
                return False
            raise
        return True

    def _endpoint(self, value: object, *, field: str, request_id: str) -> str:
        url = _text(value, field=field, maximum=2048)
        try:
            parsed = urlsplit(url)
        except ValueError as exc:
            raise ContractError(
                f"the Identity {field} is invalid",
                request_id=request_id,
            ) from exc
        if (
            not _trusted_scheme(url)
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or not _same_origin(url, self.issuer_url)
        ):
            raise ContractError(
                f"the Identity {field} is not a trusted HTTPS endpoint",
                request_id=request_id,
            )
        return url.rstrip("/")

    def _validate_browser_url(self, url: str, *, request_id: str) -> None:
        try:
            parsed = urlsplit(url)
        except ValueError as exc:
            raise ContractError(
                "the Identity verification URL is invalid",
                request_id=request_id,
            ) from exc
        if (
            not _trusted_scheme(url)
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or not _same_origin(url, self.issuer_url)
        ):
            raise ContractError(
                "the Identity verification URL is not trusted",
                request_id=request_id,
            )

    def _request(
        self,
        endpoint: str,
        *,
        method: str = "POST",
        form: Mapping[str, str | int] | None = None,
        headers: Mapping[str, str] | None = None,
        allow_empty_response: bool = False,
    ) -> JsonResponse:
        try:
            parsed = urlsplit(endpoint)
        except ValueError as exc:
            raise ConfigError("the Identity endpoint is invalid") from exc
        if not _same_origin(endpoint, self.issuer_url) or parsed.query or parsed.fragment:
            raise ConfigError("the Identity endpoint is invalid")
        path = self._relative_path(parsed.path or "/")
        return self.transport.request(
            method,
            path,
            headers=headers,
            form_body=form,
            allow_empty_response=allow_empty_response,
        )

    def _relative_path(self, endpoint_path: str) -> str:
        """Map an absolute discovered path onto the configured transport base."""

        base_path = urlsplit(self.transport.base_url).path.rstrip("/")
        path = endpoint_path or "/"
        if base_path and path == base_path:
            return "/"
        if base_path and path.startswith(f"{base_path}/"):
            return path[len(base_path) :]
        return path if path.startswith("/") else f"/{path}"

    @staticmethod
    def _parse_token_response(
        payload: Mapping[str, object],
        *,
        now: int,
        request_id: str,
    ) -> DeviceTokenResult:
        token_type = payload.get("token_type", "Bearer")
        if not isinstance(token_type, str) or token_type.lower() != "bearer":
            raise ContractError("the Identity token type is invalid", request_id=request_id)
        access_token = _token(payload.get("access_token"), field="access_token")
        expires_in = _positive_int(
            payload.get("expires_in"),
            field="expires_in",
            minimum=60,
            maximum=3600,
        )
        refresh_token = _token(payload.get("refresh_token"), field="refresh_token")
        refresh_expires_in = payload.get("refresh_expires_in")
        if refresh_expires_in is None:
            refresh_expires_in = payload.get("refresh_token_expires_in")
        if refresh_expires_in is None:
            refresh_expires_at = payload.get("refresh_expires_at")
            if type(refresh_expires_at) is not int:
                raise ContractError(
                    "the Identity refresh expiry is missing",
                    request_id=request_id,
                )
        else:
            refresh_expires_in = _positive_int(
                refresh_expires_in,
                field="refresh_expires_in",
                minimum=24 * 60 * 60,
                maximum=2**63 - 1,
            )
            refresh_expires_at = now + refresh_expires_in
        if type(refresh_expires_at) is not int or refresh_expires_at <= now + expires_in:
            raise ContractError(
                "the Identity refresh expiry is invalid",
                request_id=request_id,
            )
        subject = payload.get("subject")
        if subject is not None:
            subject = _text(subject, field="subject", maximum=512)
        device_id = payload.get("device_id")
        if device_id is not None:
            device_id = _text(device_id, field="device_id", maximum=128)
        return DeviceTokenResult(
            access_token=access_token,
            access_expires_at=now + expires_in,
            refresh_token=refresh_token,
            refresh_expires_at=refresh_expires_at,
            subject=subject,
            device_id=device_id,
        )


__all__ = [
    "DEVICE_GRANT_TYPE",
    "DeviceAuthorization",
    "DeviceTokenResult",
    "OidcClient",
    "OidcMetadata",
    "OidcPending",
    "OidcSlowDown",
]
