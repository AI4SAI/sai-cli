from __future__ import annotations

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import StringIO
import json
import shlex
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
    requested_scope: str = ""
    granted_scope: str | None = None
    token_suffix: str = ""
    access_scopes: dict[str, set[str]]


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
            self.server.requested_scope = body["scope"]
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
            token = "opaque-access-token" + self.server.token_suffix
            granted = self.server.granted_scope or self.server.requested_scope
            self.server.access_scopes[token] = set(granted.split())
            self._json(
                {
                    "token_type": "Bearer",
                    "access_token": token,
                    "expires_in": 300,
                    "refresh_token": "opaque-refresh-token" + self.server.token_suffix,
                    "subject": "subject-1",
                    "device_id": "device-id-1",
                    **({"scope": self.server.granted_scope} if self.server.granted_scope is not None else {}),
                }
            )
            return
        if self.path == "/oauth/revoke":
            self._json({})
            return
        self._json({"ok": True})

    def do_GET(self) -> None:  # noqa: N802
        self.server.requests.append({"path": self.path, "authorization": self.headers.get("Authorization")})
        if self.path.startswith("/v1/account/cli/invitations"):
            token = self.headers.get("Authorization", "").removeprefix("Bearer ")
            if "sai.collaboration.invitations.read" not in self.server.access_scopes.get(token, set()):
                self._json({"detail": {"code": "identity_scope_denied"}}, 403)
            elif self.path.startswith("/v1/account/cli/invitations?"):
                self._json({"schema_version": "collaboration.invitations/v2", "items": [],
                            "count": 0, "has_more": False, "next_cursor": None})
            else:
                from test_invitations import sample
                self._json(sample())
            return
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
    server.access_scopes = {}
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
                assert err.getvalue() == f"请运行 sai auth login --base-url {base_url} 完成 CLI 登录。\n身份认证：{base_url}/portal/#/portal/account/identity-assurance\n"
            else:
                assert json.loads(err.getvalue())["error"]["code"] == "credentials_unavailable"
        assert server.requests == []
        cache = tmp_path / "data/sai/credentials.json"
        cache.parent.mkdir(parents=True, mode=0o700)
        cache.write_text('{"version":1,"entries":{}}')
        cache.chmod(0o644)
        cache_error = StringIO()
        assert main(["auth", "status", "--format", "table", "--base-url", base_url, "--site", "site-a"],
                    environ=_env(tmp_path, identity_issuer=base_url), stdout=StringIO(), stderr=cache_error) == 3
        assert "permissions are not private" in cache_error.getvalue()
        assert "sai auth login" not in cache_error.getvalue()


def test_task_consent_preserves_session_until_approved_and_survives_resume_refresh(tmp_path: Path) -> None:
    from sai_cli.cli import build_parser
    from sai_cli.config import resolve_settings
    from sai_cli.auth import TokenProvider
    from sai_cli.cli import _build_oidc_client, _build_transport

    with _server() as (origin, server):
        profile = tmp_path / "config.toml"
        profile.write_text(f'default_profile = "device"\n[profiles.device]\nbase_url = "{origin}"\n'
                           f'identity_issuer = "{origin}"\noidc_scope = "openid offline_access"\n')
        profile.chmod(0o600)
        original_profile = profile.read_bytes()
        env = _env(tmp_path)

        def call(words, expected=0):
            out, err = StringIO(), StringIO()
            assert main(["--config", str(profile), *words], environ=env, stdout=out, stderr=err) == expected, err.getvalue()
            assert "opaque-access-token" not in out.getvalue() + err.getvalue()
            assert "opaque-refresh-token" not in out.getvalue() + err.getvalue()
            assert profile.read_bytes() == original_profile
            return json.loads(out.getvalue() if expected == 0 else err.getvalue())

        call(["auth", "login"])
        assert "sai auth login --for invitations list" in call(["invitations", "list"], 4)["error"]["message"]
        assert "sai auth login --for invitations show" in call(["invitations", "accept", "invitation-example"], 4)["error"]["message"]
        server.token_suffix = "-invitation-reads"
        read_scopes = {"openid", "offline_access", "sai.collaboration.invitations.read"}
        assert set(call(["auth", "login", "--for", "invitations", "show"])["scopes"]) == read_scopes
        assert call(["invitations", "accept", "invitation-example"])["invitation"]["status"] == "pending"
        server.token_suffix = "-invitations"
        pending = call(["auth", "login", "--for", "invitations", "accept", "--no-wait"])
        required = {"openid", "offline_access", "sai.collaboration.invitations.read", "sai.collaboration.invitations.accept"}
        assert set(pending["requested_scopes"]) == required
        # The old session keeps working while browser consent is pending.
        assert set(call(["auth", "status"])["scopes"]) == read_scopes
        assert next(item for item in reversed(server.requests) if "authorization" in item)["authorization"] == "Bearer opaque-access-token-invitation-reads"
        assert set(call(["auth", "login", "--resume"])["scopes"]) == required
        assert call(["invitations", "list"])["items"] == []

        args = build_parser().parse_args(["--config", str(profile), "auth", "status"])
        settings = resolve_settings(args, env, require_site=False)
        provider = TokenProvider(settings=settings, transport=_build_transport(settings), environ=env,
                                 oidc_client=_build_oidc_client(settings))
        provider.credential_cache.delete(provider._device_access_key())
        # Refresh omits scope: retain the original grant, not the profile baseline.
        assert set(call(["auth", "status"])["scopes"]) == required
        assert server.requests[-2]["body"]["grant_type"] == "refresh_token"
        assert call(["invitations", "list"])["items"] == []

        server.token_suffix = "-defaults"
        granted = call(["auth", "login", "--for", "account", "set-default"])
        required |= {"sai.compute.read", "sai.compute.defaults.write"}
        assert set(granted["scopes"]) == required
        assert set(server.requested_scope.split()) == required
        assert all(item["path"].startswith(("/oauth/", "/.well-known/", "/v1/account/cli/status", "/v1/account/cli/invitations")) for item in server.requests)

        server.token_suffix = "-under-granted"
        server.granted_scope = "openid offline_access"
        call(["auth", "login", "--for", "jobs", "charges", "--no-wait"])
        assert call(["auth", "login", "--resume"], 4)["error"]["code"] == "identity_scope_not_granted"
        assert set(call(["auth", "status"])["scopes"]) == required
        assert next(item for item in reversed(server.requests) if "authorization" in item)["authorization"] == "Bearer opaque-access-token-defaults"
        assert provider.pending_device_code() is None
        # A narrowed refresh grant is authoritative; do not retain removed rights.
        provider.credential_cache.delete(provider._device_access_key())
        assert set(call(["auth", "status"])["scopes"]) == {"openid", "offline_access"}
        call(["invitations", "list"], 4)
        call(["auth", "logout"])
        call(["auth", "status"], 3)
        assert json.loads((tmp_path / "data/sai/credentials.json").read_text())["entries"] == {}


def test_task_authorization_rejects_invalid_or_local_target_before_network(tmp_path: Path) -> None:
    with _server() as (origin, server):
        for suffix in (["--for", "jobs", "local"], ["--for", "unknown"],
                       ["--for", "account", "set-default", "--resume"]):
            out, err = StringIO(), StringIO()
            assert main(["auth", "login", "--base-url", origin, *suffix],
                        environ=_env(tmp_path, identity_issuer=origin), stdout=out, stderr=err) == 2
            assert not out.getvalue() and not server.requests


def test_emitted_login_permission_and_resume_commands_keep_the_selected_profile(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv('NO_PROXY', '127.0.0.1,localhost')
    with _server() as (selected, server), _server() as (other, untouched):
        config = tmp_path / "research $(untrusted) profile.toml"
        config.write_text(f'default_profile="other"\n[profiles.other]\nbase_url="{other}"\nidentity_issuer="{other}"\n'
                          f'[profiles.research]\nbase_url="{selected}"\nidentity_issuer="{selected}"\n'
                          'oidc_scope="openid offline_access"\n')
        config.chmod(0o600)
        original = config.read_bytes()
        env = {**_env(tmp_path), 'XDG_CONFIG_HOME':str(tmp_path/'unconfigured')}
        selection = ['--config', str(config), '--profile', 'research']
        def call(words, expected=0):
            out, err = StringIO(), StringIO()
            assert main(words, environ=env, stdout=out, stderr=err) == expected, err.getvalue()
            assert not untouched.requests and config.read_bytes() == original
            return json.loads(out.getvalue() if expected == 0 else err.getvalue())
        def follow(message):
            return shlex.split(message.split('`')[1])[1:]
        missing = call(['auth', 'status', *selection], 3)
        login = follow(missing['error']['message'])
        pending = call([*login, '--no-wait'])
        resume = shlex.split(pending['resume'])[1:]
        assert '--for' not in resume
        call(resume)
        denied = call([*selection, 'invitations', 'list'], 4)
        consent = follow(denied['error']['message'])
        pending = call([*consent, '--no-wait'])
        assert 'sai.collaboration.invitations.read' in pending['requested_scopes']
        call(shlex.split(pending['resume'])[1:])
        assert call(['invitations', 'list', *selection])['items'] == []
        assert server.poll_count == 2


def test_permission_upgrade_keeps_connection_and_baseline_contexts_isolated(tmp_path: Path) -> None:
    with _server() as (origin, server):
        env = _env(tmp_path, identity_issuer=origin)
        env["SAI_API_BASE_URL"] = origin
        assert main(["auth", "login", "--for", "invitations"], environ=env,
                    stdout=StringIO(), stderr=StringIO()) == 0
        for changed in [
            {"SAI_OIDC_SCOPE": "openid offline_access sai.billing.read"},
            {"SAI_OIDC_CLIENT_ID": "another-client"},
            {"SAI_OIDC_RESOURCE": "another-resource"},
            {"SAI_IDENTITY_ISSUER": origin + "/another-realm"},
            {"SAI_API_BASE_URL": origin + "/another-portal"},
        ]:
            before = len(server.requests)
            out, err = StringIO(), StringIO()
            assert main(["auth", "status"], environ={**env, **changed}, stdout=out, stderr=err) == 3
            assert not out.getvalue() and len(server.requests) == before
        assert main(["invitations", "list"], environ=env, stdout=StringIO(), stderr=StringIO()) == 0
