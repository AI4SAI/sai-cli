"""Bounded JSON-over-HTTP transport with safe error rendering."""

from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import json
import re
import socket
from typing import Any, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, OpenerDirector, Request, build_opener
import uuid

from . import __version__
from .errors import (
    AuthenticationError,
    ConfigError,
    ContractError,
    ForbiddenError,
    NetworkError,
    NotFoundError,
    SaiCliError,
    UnavailableError,
)


_MAX_RESPONSE_BYTES = 4 * 1024 * 1024
_MAX_ERROR_BYTES = 64 * 1024
_MAX_REQUEST_BYTES = 64 * 1024
_SAFE_CODE_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,96}$")
_BEARER_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
_SECRET_PAIR_RE = re.compile(
    r"(?i)\b(token|secret|password|passwd|authorization|signature|sig)\b\s*[:=]\s*[^\s,;]+"
)
_PRIVATE_PATH_RE = re.compile(r"(?<![A-Za-z0-9_])/(?:home|tmp)/[^\s,;]+")
_PRIVATE_IP_RE = re.compile(
    r"(?<!\d)(?:10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2})(?!\d)"
)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


@dataclass(frozen=True)
class JsonResponse:
    payload: dict[str, Any]
    request_id: str
    status: int


def _is_loopback_host(hostname: str | None) -> bool:
    if not hostname:
        return False
    lowered = hostname.rstrip(".").lower()
    if lowered == "localhost" or lowered.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(lowered).is_loopback
    except ValueError:
        return False


def normalize_base_url(base_url: str, *, allow_insecure_http: bool) -> str:
    value = (base_url or "").strip().rstrip("/")
    try:
        parsed = urlsplit(value)
    except ValueError as exc:
        raise ConfigError("the SAI API base URL is invalid") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ConfigError("the SAI API base URL must use http or https")
    if parsed.username or parsed.password:
        raise ConfigError("credentials are not allowed in the SAI API base URL")
    if parsed.query or parsed.fragment:
        raise ConfigError("the SAI API base URL cannot contain a query or fragment")
    if parsed.scheme == "http" and not (_is_loopback_host(parsed.hostname) or allow_insecure_http):
        raise ConfigError("plain HTTP is allowed only for loopback development endpoints")
    return value


def sanitize_message(value: object, *, fallback: str) -> str:
    if not isinstance(value, str):
        return fallback
    text = " ".join(value.split())[:512]
    text = _BEARER_RE.sub("Bearer [redacted]", text)
    text = _SECRET_PAIR_RE.sub(lambda match: f"{match.group(1)}=[redacted]", text)
    text = _PRIVATE_PATH_RE.sub("[private-path]", text)
    text = _PRIVATE_IP_RE.sub("[private-address]", text)
    return text[:240] or fallback


def _bounded_error(payload: object, *, status: int) -> tuple[str, str]:
    fallback_code = f"http_{status}"
    fallback_message = f"the SAI API rejected the request (HTTP {status})"
    if not isinstance(payload, dict):
        return fallback_code, fallback_message

    # OAuth/OIDC token endpoints use the RFC 6749 ``error`` and
    # ``error_description`` members rather than Portal's ``detail`` envelope.
    oauth_code = payload.get("error")
    if isinstance(oauth_code, str) and _SAFE_CODE_RE.fullmatch(oauth_code):
        return oauth_code, sanitize_message(
            payload.get("error_description"),
            fallback=fallback_message,
        )

    detail = payload.get("detail")
    if isinstance(detail, dict):
        raw_code = detail.get("code")
        code = raw_code if isinstance(raw_code, str) and _SAFE_CODE_RE.fullmatch(raw_code) else fallback_code
        message = sanitize_message(detail.get("message"), fallback=fallback_message)
        return code, message
    if isinstance(detail, str):
        return fallback_code, sanitize_message(detail, fallback=fallback_message)

    raw_code = payload.get("code")
    code = raw_code if isinstance(raw_code, str) and _SAFE_CODE_RE.fullmatch(raw_code) else fallback_code
    return code, sanitize_message(payload.get("message"), fallback=fallback_message)


def _http_error(*, status: int, payload: object, request_id: str | None) -> SaiCliError:
    code, message = _bounded_error(payload, status=status)
    if status == 401:
        return AuthenticationError(message, code=code, request_id=request_id)
    if status == 403:
        return ForbiddenError(message, code=code, request_id=request_id)
    if status == 404:
        return NotFoundError(message, code=code, request_id=request_id)
    if status in {408, 429, 500, 502, 503, 504}:
        return UnavailableError(message, code=code, request_id=request_id)
    if status in {400, 405, 409, 410, 422}:
        return ConfigError(message, code=code)
    return UnavailableError(message, code=code, request_id=request_id)


def _decode_json(
    data: bytes,
    *,
    request_id: str,
    error_body: bool = False,
    allow_empty: bool = False,
) -> dict[str, Any]:
    if not data:
        if error_body:
            return {}
        if allow_empty:
            return {}
        raise ContractError(request_id=request_id)
    try:
        decoded = data.decode("utf-8", errors="strict")
        payload = json.loads(decoded)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        if error_body:
            return {}
        raise ContractError(request_id=request_id) from exc
    if not isinstance(payload, dict):
        if error_body:
            return {}
        raise ContractError(request_id=request_id)
    return payload


class JsonTransport:
    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float,
        allow_insecure_http: bool = False,
        opener: OpenerDirector | None = None,
        max_response_bytes: int = _MAX_RESPONSE_BYTES,
    ) -> None:
        self.base_url = normalize_base_url(base_url, allow_insecure_http=allow_insecure_http)
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes
        self._opener = opener or build_opener(_NoRedirect())

    def request(
        self,
        method: str,
        path: str,
        *,
        query: Mapping[str, str | int | Sequence[str] | None] | None = None,
        headers: Mapping[str, str] | None = None,
        json_body: Mapping[str, object] | None = None,
        form_body: Mapping[str, str | int] | None = None,
        allow_empty_response: bool = False,
    ) -> JsonResponse:
        if not path.startswith("/") or path.startswith("//"):
            raise ConfigError("API request path is invalid")
        request_id = f"sai-cli-{uuid.uuid4().hex}"
        encoded_query = urlencode(
            [(key, value) for key, raw in (query or {}).items() for value in _query_values(raw)],
            doseq=False,
        )
        url = f"{self.base_url}{path}"
        if encoded_query:
            url = f"{url}?{encoded_query}"
        request_headers = {
            "Accept": "application/json",
            "User-Agent": f"sai-cli/{__version__}",
            "X-SAI-Request-ID": request_id,
        }
        request_headers.update(headers or {})
        data: bytes | None = None
        if json_body is not None and form_body is not None:
            raise ConfigError("API request cannot contain both JSON and form bodies")
        if json_body is not None:
            if method.upper() not in {"POST", "PUT", "PATCH"}:
                raise ConfigError("JSON request bodies require POST, PUT, or PATCH")
            try:
                data = json.dumps(
                    dict(json_body),
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
            except (TypeError, ValueError) as exc:
                raise ConfigError("API request body is invalid") from exc
            if len(data) > _MAX_REQUEST_BYTES:
                raise ConfigError("API request body is too large")
            request_headers["Content-Type"] = "application/json"
        elif form_body is not None:
            if method.upper() not in {"POST", "PUT", "PATCH"}:
                raise ConfigError("form request bodies require POST, PUT, or PATCH")
            if any(
                not isinstance(key, str)
                or not key
                or not isinstance(value, (str, int))
                or isinstance(value, bool)
                for key, value in form_body.items()
            ):
                raise ConfigError("API form body is invalid")
            data = urlencode(
                [(key, value) for key, value in form_body.items()],
                doseq=False,
            ).encode("utf-8")
            if len(data) > _MAX_REQUEST_BYTES:
                raise ConfigError("API request body is too large")
            request_headers["Content-Type"] = "application/x-www-form-urlencoded"
        request = Request(
            url=url,
            data=data,
            method=method.upper(),
            headers=request_headers,
        )

        try:
            with self._opener.open(request, timeout=self.timeout_seconds) as response:
                response_request_id = response.headers.get("X-Request-ID") or response.headers.get("X-SAI-Request-ID") or request_id
                content_length = response.headers.get("Content-Length")
                if content_length and content_length.isdigit() and int(content_length) > self.max_response_bytes:
                    raise ContractError("the server response is too large", request_id=response_request_id)
                data = response.read(self.max_response_bytes + 1)
                if len(data) > self.max_response_bytes:
                    raise ContractError("the server response is too large", request_id=response_request_id)
                payload = _decode_json(
                    data,
                    request_id=response_request_id,
                    allow_empty=allow_empty_response,
                )
                return JsonResponse(payload=payload, request_id=response_request_id, status=int(response.status))
        except HTTPError as exc:
            response_request_id = exc.headers.get("X-Request-ID") or exc.headers.get("X-SAI-Request-ID") or request_id
            data = exc.read(_MAX_ERROR_BYTES + 1)
            payload = _decode_json(data[:_MAX_ERROR_BYTES], request_id=response_request_id, error_body=True)
            raise _http_error(
                status=int(exc.code),
                payload=payload,
                request_id=response_request_id,
            ) from None
        except SaiCliError:
            raise
        except (URLError, TimeoutError, socket.timeout, ConnectionError, OSError) as exc:
            raise NetworkError(request_id=request_id) from exc


def _query_values(raw: str | int | Sequence[str] | None) -> list[str | int]:
    if raw is None:
        return []
    if isinstance(raw, (str, int)) and not isinstance(raw, bool):
        return [raw]
    if isinstance(raw, Sequence):
        return [str(value) for value in raw]
    raise ConfigError("API query value is invalid")
