from __future__ import annotations

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import StringIO
import json
from pathlib import Path
import threading
import time
from typing import Any, Iterator
from urllib.parse import parse_qs

from sai_cli.cli import main


class _AuthServer(ThreadingHTTPServer):
    requests: list[dict[str, Any]]
    poll_count: int = 0
    account_status_code: int = 200


class _AuthHandler(BaseHTTPRequestHandler):
    server: _AuthServer

    def _json(self, payload: dict[str, Any], status: int = 200) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("X-Request-ID", "auth-request")
        self.end_headers()
        self.wfile.write(encoded)

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        raw_body = self.rfile.read(length) or b""
        body = (
            json.loads(raw_body)
            if self.headers.get("Content-Type", "").startswith("application/json")
            else {key: values[-1] for key, values in parse_qs(raw_body.decode()).items()}
        )
        self.server.requests.append({"path": self.path, "body": body})
        if self.path == "/oauth/device":
            host, port = self.server.server_address
            self._json(
                {
                    "device_code": "device-code-opaque",
                    "user_code": "ABCD-EFGH",
                    "verification_uri": f"http://{host}:{port}/authorize",
                    "expires_in": 300,
                    "interval": 1,
                }
            )
            return
        if self.path == "/oauth/token":
            self.server.poll_count += 1
            now = int(time.time())
            self._json(
                {
                    "token_type": "Bearer",
                    "access_token": "opaque-access-token",
                    "expires_in": 300,
                    "refresh_token": "opaque-refresh-token",
                    "subject": "subject-1",
                    "device_id": "device-id-1",
                }
            )
            return
        if self.path == "/oauth/revoke":
            self._json({})
            return
        self._json({"ok": True})

    def do_GET(self) -> None:  # noqa: N802
        self.server.requests.append({"path": self.path, "authorization": self.headers.get("Authorization")})
        if self.path == "/v1/account/cli/status":
            if self.server.account_status_code != 200:
                self._json({"detail": {"code": "account_status_unavailable", "message": "Account status unavailable"}}, self.server.account_status_code)
                return
            self._json({
                "schema_version": "account.status/v1",
                "verification_current": True,
                "access_state": "normal",
                "initial_verification_deadline": None,
                "verification_url": "/portal/#/portal/account/identity-assurance",
            })
            return
        if self.path == "/.well-known/openid-configuration":
            host, port = self.server.server_address
            self._json(
                {
                    "issuer": f"http://{host}:{port}",
                    "device_authorization_endpoint": f"http://{host}:{port}/oauth/device",
                    "token_endpoint": f"http://{host}:{port}/oauth/token",
                    "revocation_endpoint": f"http://{host}:{port}/oauth/revoke",
                    "userinfo_endpoint": f"http://{host}:{port}/userinfo",
                }
            )
            return
        self._json({"ok": True})

    def log_message(self, _format: str, *_args: object) -> None:
        return


@contextmanager
def _server() -> Iterator[tuple[str, _AuthServer]]:
    server = _AuthServer(("127.0.0.1", 0), _AuthHandler)
    server.requests = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}", server
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def _env(tmp_path: Path, *, identity_issuer: str = "") -> dict[str, str]:
    return {
        "XDG_DATA_HOME": str(tmp_path / "data"),
        "XDG_CACHE_HOME": str(tmp_path / "cache"),
        **({"SAI_IDENTITY_ISSUER": identity_issuer} if identity_issuer else {}),
    }


def test_device_login_status_and_logout_round_trip(tmp_path: Path) -> None:
    with _server() as (base_url, server):
        stdout = StringIO()
        stderr = StringIO()
        result = main(
            ["auth", "login", "--base-url", base_url],
            environ=_env(tmp_path, identity_issuer=base_url),
            stdout=stdout,
            stderr=stderr,
        )
        assert result == 0
        login_payload = json.loads(stdout.getvalue())
        assert login_payload["authenticated"] is True
        assert login_payload["refresh_expires_at"] is None
        assert "opaque-access-token" not in stdout.getvalue()
        assert "opaque-refresh-token" not in stdout.getvalue()
        assert "ABCD-EFGH" in stderr.getvalue()
        assert any(item["path"] == "/oauth/device" for item in server.requests)
        assert any(item["path"] == "/oauth/token" for item in server.requests)

        status_out = StringIO()
        status_err = StringIO()
        assert main(
            ["auth", "status", "--base-url", base_url],
            environ=_env(tmp_path, identity_issuer=base_url),
            stdout=status_out,
            stderr=status_err,
        ) == 0
        status_payload = json.loads(status_out.getvalue())
        assert status_payload["issuer"] == base_url
        assert status_payload["client_id"] == "sai-cli"
        assert status_payload["refresh_expires_at"] is None
        assert status_payload["account"]["verification_current"] is True
        assert status_payload["account"]["verification_url"] == base_url + "/portal/#/portal/account/identity-assurance"
        assert next(item for item in server.requests if item["path"] == "/v1/account/cli/status")["authorization"] == "Bearer opaque-access-token"
        assert "opaque-access-token" not in status_out.getvalue()
        assert status_err.getvalue() == ""
        table_out = StringIO()
        assert main(["auth", "status", "--format", "table", "--base-url", base_url, "--site", "site-a"],
                    environ=_env(tmp_path, identity_issuer=base_url), stdout=table_out, stderr=StringIO()) == 0
        assert table_out.getvalue() == f"身份认证：当前有效\n认证入口：{base_url}/portal/#/portal/account/identity-assurance\n"
        for status_code, expected_exit in ((401, 3), (503, 6)):
            server.account_status_code = status_code
            failure_out, failure_err = StringIO(), StringIO()
            assert main(["auth", "status", "--format", "table", "--base-url", base_url, "--site", "site-a"],
                        environ=_env(tmp_path, identity_issuer=base_url), stdout=failure_out, stderr=failure_err) == expected_exit
            assert failure_out.getvalue() == ""
            assert ("sai auth login" in failure_err.getvalue()) == (status_code == 401)
            assert ("ERROR [account_status_unavailable]" in failure_err.getvalue()) == (status_code == 503)
            assert "opaque-access-token" not in failure_err.getvalue()

        logout_out = StringIO()
        assert main(
            ["auth", "logout", "--base-url", base_url],
            environ=_env(tmp_path, identity_issuer=base_url),
            stdout=logout_out,
            stderr=StringIO(),
        ) == 0
        assert json.loads(logout_out.getvalue()) == {
            "local_cleared": True,
            "ok": True,
            "revoked": True,
        }

    credentials_path = tmp_path / "data" / "sai" / "credentials.json"
    assert credentials_path.exists()
    assert json.loads(credentials_path.read_text(encoding="utf-8"))["entries"] == {}


def test_legacy_environment_token_status_does_not_require_identity(tmp_path: Path) -> None:
    stdout = StringIO()
    stderr = StringIO()
    result = main(
        ["auth", "status", "--base-url", "https://portal.example.org", "--site", "site-a"],
        environ={**_env(tmp_path), "SAI_TOKEN": "compat-token"},
        stdout=stdout,
        stderr=stderr,
    )
    assert result == 0
    payload = json.loads(stdout.getvalue())
    assert payload["authenticated"] is True
    assert payload["source"] == "environment"
    assert "compat-token" not in stdout.getvalue()


def test_device_login_without_identity_issuer_is_bounded(tmp_path: Path) -> None:
    stdout = StringIO()
    stderr = StringIO()
    result = main(
        ["auth", "login", "--no-wait", "--base-url", "https://portal.example.org", "--site", "site-a"],
        environ=_env(tmp_path),
        stdout=stdout,
        stderr=stderr,
    )
    assert result == 3
    assert json.loads(stderr.getvalue())["error"]["code"] == "credentials_unavailable"
    assert stdout.getvalue() == ""


def test_status_without_credentials_gives_login_action_without_starting_authorization(tmp_path: Path) -> None:
    with _server() as (base_url, server):
        for output_format in ("table", "json"):
            out, err = StringIO(), StringIO()
            assert main(["auth", "status", "--format", output_format, "--base-url", base_url, "--site", "site-a"],
                        environ=_env(tmp_path, identity_issuer=base_url), stdout=out, stderr=err) == 3
            assert out.getvalue() == ""
            if output_format == "table":
                assert err.getvalue() == f"请运行 sai auth login 完成 CLI 登录。\n身份认证：{base_url}/portal/#/portal/account/identity-assurance\n"
            else:
                assert json.loads(err.getvalue())["error"]["code"] == "credentials_unavailable"
        assert server.requests == []
        cache = tmp_path / "cache/sai/token-cache.json"
        cache.parent.mkdir(parents=True, mode=0o700)
        cache.write_text('{"version":1,"entries":{}}')
        cache.chmod(0o644)
        cache_error = StringIO()
        assert main(["auth", "status", "--format", "table", "--base-url", base_url, "--site", "site-a"],
                    environ=_env(tmp_path, identity_issuer=base_url), stdout=StringIO(), stderr=cache_error) == 3
        assert "permissions are not private" in cache_error.getvalue()
        assert "sai auth login" not in cache_error.getvalue()
