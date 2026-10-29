"""Recovery actions retain task and connection context across real CLI boundaries."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

import pytest

from sai_cli.cli import build_parser
from sai_cli.errors import SaiCliError
from sai_cli.tui_queries import Queries
from test_cli_auth import _server
from test_site_transport import http_endpoint


_SOURCE = Path(__file__).resolve().parents[1] / "src"
_BASELINE = "openid offline_access"
_INVITATION_READ = "sai.collaboration.invitations.read"
_INVITATION_ACCEPT = "sai.collaboration.invitations.accept"


def _environment(root):
    binary_directory = root / "bin"
    binary_directory.mkdir()
    entry = binary_directory / "sai"
    entry.write_text(f"#!{sys.executable}\nimport os,sys\nfrom pathlib import Path\n"
        f"sys.path.insert(0,{str(_SOURCE)!r})\n"
        "if 'TEST_MANAGED_CONFIG' in os.environ:\n"
        "    from sai_cli import config\n"
        "    config._MANAGED_CONFIG_PATH=Path(os.environ['TEST_MANAGED_CONFIG'])\n"
        "    config._MANAGED_CONFIG_OWNER_UID=os.getuid()\n"
        "from sai_cli.cli import entrypoint\nentrypoint()\n")
    entry.chmod(0o755)
    return {"PATH": str(binary_directory) + os.pathsep + os.defpath, "NO_PROXY": "*",
            "PYTHONDONTWRITEBYTECODE": "1", "XDG_CONFIG_HOME": str(root / "config"),
            "XDG_DATA_HOME": str(root / "data"), "XDG_CACHE_HOME": str(root / "cache")}


def _profile(root, origin, *, issuer=None, baseline=_BASELINE, filename="service choices.toml", other=None):
    path = root / filename
    values = {"base_url": origin, "identity_issuer": issuer or origin, "site_id": "site-a",
              "cluster_id": "cluster-a", "oidc_scope": baseline}
    text = 'default_profile = "other"\n[profiles.other]\nbase_url = ' + json.dumps(other or origin) + "\n"
    text += '[profiles.research]\n' + "".join(f"{key} = {json.dumps(value)}\n" for key, value in values.items())
    path.write_text(text)
    path.chmod(0o600)
    return path


def _selection(profile):
    return ["--config", str(profile), "--profile", "research"]


def _run(argv, env, *, cwd, expected=0):
    completed = subprocess.run(argv, env=env, cwd=cwd, capture_output=True, text=True,
                               encoding="utf-8", shell=False, timeout=6)
    assert completed.returncode == expected, completed.stderr
    if expected:
        assert not completed.stdout
        assert completed.stderr.count("\n") == 1
    assert "opaque-access-token" not in completed.stdout + completed.stderr
    assert "opaque-refresh-token" not in completed.stdout + completed.stderr
    return completed


def _error(completed):
    return json.loads(completed.stderr)["error"]


@pytest.mark.parametrize("filename", ["research $(echo untrusted) choices.toml", "research choices\nline\u0085.toml"])
def test_missing_session_argv_executes_without_shell_and_preserves_selected_service(tmp_path, filename):
    env = _environment(tmp_path)
    with _server() as (selected, server), _server() as (other, untouched):
        profile = _profile(tmp_path, selected, filename=filename, other=other)
        original = profile.read_bytes()
        command = ["sai", "invitations", "list", "--config", profile.name, "--profile", "research"]
        failed = _run(command, env, cwd=tmp_path, expected=3)
        error = _error(failed)
        assert error["code"] == "credentials_unavailable"
        argv = error["recovery"]["argv"]
        assert argv[:6] == ["sai", "auth", "login", "--for", "invitations", "list"]
        assert argv[argv.index("--config") + 1] == str(profile)
        assert argv[argv.index("--profile") + 1] == "research"
        assert "\u0085" not in failed.stderr
        assert not server.requests and not untouched.requests
        elsewhere = tmp_path / "another working directory"
        elsewhere.mkdir()
        pending = _run([*argv, "--no-wait"], env, cwd=elsewhere)
        assert "\u0085" not in pending.stdout
        authorization = json.loads(pending.stdout)
        assert authorization["resume_argv"][authorization["resume_argv"].index("--config") + 1] == str(profile)
        login = _run(authorization["resume_argv"], env, cwd=elsewhere)
        assert json.loads(login.stdout)["authenticated"] is True
        assert set(server.requested_scope.split()) == {"openid", "offline_access", _INVITATION_READ}
        assert json.loads(_run(command, env, cwd=tmp_path).stdout)["items"] == []
        assert profile.read_bytes() == original and not untouched.requests


def test_baseline_permission_needs_no_redundant_task_authorization(tmp_path):
    env = _environment(tmp_path)
    with _server() as (origin, server):
        profile = _profile(tmp_path, origin, baseline=_BASELINE + " " + _INVITATION_READ)
        error = _error(_run(["sai", "invitations", "list", *_selection(profile)], env, cwd=tmp_path, expected=3))
        argv = error["recovery"]["argv"]
        assert argv[:3] == ["sai", "auth", "login"] and "--for" not in argv
        _run(argv, env, cwd=tmp_path)
        assert set(server.requested_scope.split()) == {"openid", "offline_access", _INVITATION_READ}


def test_auth_status_recovery_does_not_request_business_permissions(tmp_path):
    env = _environment(tmp_path)
    with _server() as (origin, server):
        profile = _profile(tmp_path, origin)
        error = _error(_run(["sai", "auth", "status", *_selection(profile)], env, cwd=tmp_path, expected=3))
        argv = error["recovery"]["argv"]
        assert argv[:3] == ["sai", "auth", "login"] and "--for" not in argv
        _run(argv, env, cwd=tmp_path)
        assert set(server.requested_scope.split()) == {"openid", "offline_access"}


@pytest.mark.parametrize("command", [["status"], ["auth", "status"], ["invitations", "list"]])
def test_disabled_session_storage_does_not_offer_a_login_that_cannot_be_reused(tmp_path, command):
    env = _environment(tmp_path)
    with _server() as (origin, server):
        profile = _profile(tmp_path, origin)
        failed = _run(["sai", *command, "--no-cache", *_selection(profile)], env, cwd=tmp_path, expected=3)
        error = _error(failed)
        assert error["code"] == "device_session_disabled"
        assert "recovery" not in error and "--no-cache" in error["message"]
        assert not server.requests
        human = _run(["sai", *command, "--no-cache", "--format", "table", *_selection(profile)],
                     env, cwd=tmp_path, expected=3)
        assert "sai auth login" not in human.stderr
        assert not server.requests


def test_existing_session_scope_denial_has_an_executable_task_action_and_request_id(tmp_path):
    env = _environment(tmp_path)
    with _server() as (origin, server):
        profile = _profile(tmp_path, origin)
        _run(["sai", "auth", "login", *_selection(profile)], env, cwd=tmp_path)
        command = ["sai", "invitations", "list", *_selection(profile)]
        error = _error(_run(command, env, cwd=tmp_path, expected=4))
        assert error["code"] == "identity_scope_denied" and error["request_id"] == "auth-request"
        assert error["recovery"]["argv"][:6] == ["sai", "auth", "login", "--for", "invitations", "list"]
        _run(error["recovery"]["argv"], env, cwd=tmp_path)
        assert set(server.requested_scope.split()) == {"openid", "offline_access", _INVITATION_READ}
        assert json.loads(_run(command, env, cwd=tmp_path).stdout)["items"] == []


@pytest.mark.parametrize("apply", [False, True])
def test_invitation_recovery_distinguishes_preview_from_acceptance_permission(tmp_path, apply):
    env = _environment(tmp_path)
    with _server() as (origin, server):
        profile = _profile(tmp_path, origin)
        command = ["sai", "invitations", "accept", "invitation-example", *_selection(profile)]
        if apply:
            command.append("--apply")
        error = _error(_run(command, env, cwd=tmp_path, expected=3))
        argv = error["recovery"]["argv"]
        assert argv[:6] == ["sai", "auth", "login", "--for", "invitations", "accept" if apply else "show"]
        _run(argv, env, cwd=tmp_path)
        expected = {"openid", "offline_access", _INVITATION_READ}
        if apply:
            expected.add(_INVITATION_ACCEPT)
        assert set(server.requested_scope.split()) == expected
        assert all(row["path"].startswith(("/.well-known/", "/oauth/")) for row in server.requests)
        if not apply:
            assert json.loads(_run(command, env, cwd=tmp_path).stdout)["invitation"]["status"] == "pending"
            assert not any(row["path"].endswith("/accept") for row in server.requests)


@pytest.mark.parametrize("status,code,external", [
    (403, "workspace_access_denied", False), (503, "source_unavailable", False),
    (403, "identity_scope_denied", True), (401, "authentication_failed", True),
    (503, "identity_scope_denied", False), (503, "credentials_unavailable", False),
    (401, "credentials_unavailable", True),
])
def test_service_denials_and_external_credentials_do_not_create_device_login(tmp_path, status, code, external):
    env = _environment(tmp_path)
    with _server() as (issuer, _), http_endpoint(lambda *_: (status, {"detail": {"code": code, "message": "Unavailable"}})) as (origin, calls):
        profile = _profile(tmp_path, origin, issuer=issuer)
        if external:
            env["SAI_TOKEN"] = "example-external-access"
        else:
            _run(["sai", "auth", "login", *_selection(profile)], env, cwd=tmp_path)
        command = ["sai", "invitations", "list", *_selection(profile)] + (["--no-cache"] if external else [])
        error = _error(_run(command, env,
                            cwd=tmp_path, expected={401: 3, 403: 4, 503: 6}[status]))
        assert error["code"] == code and "recovery" not in error
        assert "auth login" not in error["message"]
        assert len(calls) == 1 and calls[0]["method"] == "GET"


def test_external_access_auth_status_does_not_render_a_device_login_action(tmp_path):
    env = {**_environment(tmp_path), "SAI_TOKEN": "example-external-access"}
    with http_endpoint(lambda *_: (401, {"detail": {"code": "invalid_token", "message": "Access expired"}})) as (origin, calls):
        profile = _profile(tmp_path, origin)
        failed = _run(["sai", "auth", "status", "--format", "table", *_selection(profile)],
                      env, cwd=tmp_path, expected=3)
        assert "invalid_token" in failed.stderr and "auth login" not in failed.stderr
        assert "example-external-access" not in failed.stderr
        assert len(calls) == 1 and calls[0]["method"] == "GET"


@pytest.mark.parametrize("code", ["identity_scope_denied", "workspace_access_denied"])
def test_server_recovery_scripts_and_secret_fields_never_become_client_actions(tmp_path, code):
    forged = {"argv": ["sh", "-c", "echo provider-script-marker"], "secret": "provider-secret-marker"}
    payload = {"detail": {"code": code, "message": "Permission denied", "recovery": forged,
                          "script": "provider-script-marker", "secret": "provider-secret-marker"},
               "recovery": forged, "script": "provider-script-marker"}
    env = _environment(tmp_path)
    with _server() as (issuer, _), http_endpoint(lambda *_: (403, payload)) as (origin, _):
        profile = _profile(tmp_path, origin, issuer=issuer)
        _run(["sai", "auth", "login", *_selection(profile)], env, cwd=tmp_path)
        failed = _run(["sai", "invitations", "list", *_selection(profile)], env, cwd=tmp_path, expected=4)
        error = _error(failed)
        assert "provider-script-marker" not in failed.stderr and "provider-secret-marker" not in failed.stderr
        if code == "identity_scope_denied":
            assert error["recovery"]["argv"][:6] == ["sai", "auth", "login", "--for", "invitations", "list"]
            assert set(error["recovery"]) == {"argv"}
        else:
            assert "recovery" not in error


def test_managed_summary_recovery_uses_shared_profile_without_transient_timeout(tmp_path):
    env = _environment(tmp_path)
    with _server() as (origin, server):
        baseline = _BASELINE + " sai.compute.read sai.billing.read"
        profile = _profile(tmp_path, origin, baseline=baseline)
        profile.write_text(profile.read_text().replace('default_profile = "other"', 'default_profile = "research"')
                           + "require_site_capability = true\n")
        env.update(SAI_MANAGED_LOGIN_NODE="1", TEST_MANAGED_CONFIG=str(profile))
        error = _error(_run(["sai", "status", "--timeout", "3"], env, cwd=tmp_path, expected=3))
        assert error["recovery"]["argv"] == ["sai", "auth", "login"]
        human = subprocess.run(["sai", "status", "--timeout", "3", "--format", "table"],
            env=env, cwd=tmp_path, capture_output=True, text=True, timeout=6)
        assert human.returncode == 3 and "sai auth login" in human.stderr
        assert "--timeout" not in human.stderr and not server.requests


def test_queries_preserve_scope_error_request_id_and_recovery_from_a_real_child(tmp_path):
    env = _environment(tmp_path)
    with _server() as (origin, _):
        profile = _profile(tmp_path, origin, filename="query context\nline\u0085.toml")
        _run(["sai", "auth", "login", *_selection(profile)], env, cwd=tmp_path)
        direct = _error(_run(["sai", "invitations", "list", *_selection(profile)], env, cwd=tmp_path, expected=4))
        queries = Queries(build_parser().parse_args(["tui", *_selection(profile)]), env)

        async def run():
            with pytest.raises(SaiCliError) as caught:
                await queries._command(["invitations", "list"], remote=True)
            error = caught.value
            assert error.code == direct["code"]
            assert error.request_id == direct["request_id"] == "auth-request"
            assert list(error.recovery_argv) == direct["recovery"]["argv"]

        asyncio.run(run())


@pytest.mark.parametrize("status,code", [(403, "identity_scope_denied"), (503, "source_unavailable")])
def test_account_tui_displays_the_child_action_and_request_id_without_inventing_login(tmp_path, status, code):
    pytest.importorskip("textual")
    from textual.widgets import Static
    from sai_cli.tui import QueryApp
    from sai_cli.managed_runs import terminal_log
    from test_tui import loaded

    env = _environment(tmp_path)
    with _server() as (issuer, _), http_endpoint(lambda *_: (status, {"detail": {"code": code, "message": "Unavailable"}})) as (origin, _):
        profile = _profile(tmp_path, origin, issuer=issuer, filename="tui context\nline\u0085.toml")
        _run(["sai", "auth", "login", *_selection(profile)], env, cwd=tmp_path)
        queries = Queries(build_parser().parse_args(["tui", *_selection(profile)]), env)
        original, failures = queries.read, []

        async def read(request):
            try:
                return await original(request)
            except SaiCliError as error:
                failures.append(error)
                raise

        queries.read = read

        async def run():
            app = QueryApp(queries, initial="account")
            async with app.run_test(size=(100, 24)) as pilot:
                await loaded(app, pilot)
                assert len(failures) == 1
                error = failures[0]
                assert error.code == code and error.request_id
                visible = str(app.query_one("#content", Static).render())
                assert error.request_id in visible
                assert not app.query_one("#controls").display
                assert not str(app.query_one("#notice", Static).render())
                if status == 403:
                    command = terminal_log(shlex.join(error.recovery_argv))
                    assert error.recovery_argv[:6] == ("sai", "auth", "login", "--for", "account", "defaults")
                    assert visible.count(command) == 1
                else:
                    assert not error.recovery_argv and "auth login" not in visible
                assert "\u0085" not in visible

        asyncio.run(run())
