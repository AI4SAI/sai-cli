"""Device sessions survive ordinary cancellation, shared use and recoverable failures."""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
from urllib.parse import parse_qs

import pytest

from sai_cli.auth import DeviceTokenResult, TokenProvider
from sai_cli.cache import TokenCache
from sai_cli.cli import build_parser
from sai_cli.config import Settings
from sai_cli.errors import AuthenticationError, SaiCliError
from sai_cli.oidc import OidcClient
from sai_cli.transport import JsonTransport
from sai_cli.tui_queries import Queries


_SCOPE = "openid offline_access"
_SOURCE = str(Path(__file__).resolve().parents[1] / "src")


@contextmanager
def _issuer(*, gated=False, failure=None):
    """Single-use rotating grants; only the response timing is synthetic."""
    class Server(ThreadingHTTPServer):
        current = "example-refresh-0"
        rotations = 0
        token_calls = 0
        business_calls = 0

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, status, payload):
            body = json.dumps(payload).encode()
            try:
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self):
            if self.path == "/.well-known/openid-configuration":
                if server.failure == "discovery-invalid":
                    return self.reply(200, {"issuer": server.origin})
                if server.failure == "discovery-unauthorized":
                    return self.reply(401, {"error": "invalid_token"})
                return self.reply(200, {
                    "issuer": server.origin,
                    "device_authorization_endpoint": server.origin + "/device",
                    "token_endpoint": server.origin + "/token",
                    "revocation_endpoint": server.origin + "/revoke",
                })
            server.business_calls += 1
            self.reply(200, {
                "schema_version": "account.status/v1", "verification_current": True,
                "access_state": "normal",
                "initial_verification_deadline": None,
                "verification_url": "/portal/#/portal/account/identity-assurance",
            })

        def do_POST(self):
            form = parse_qs(self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode())
            if self.path == "/revoke":
                return self.reply(200, {})
            assert self.path == "/token"
            with server.guard:
                server.token_calls += 1
                if server.failure == "temporary":
                    return self.reply(503, {"error": "temporarily_unavailable"})
                if server.failure == "client-config":
                    return self.reply(400, {"error": "unauthorized_client"})
                if form.get("refresh_token") != [server.current]:
                    return self.reply(400, {"error": "invalid_grant"})
                server.rotations += 1
                server.current = f"example-refresh-{server.rotations}"
                result = {
                    "access_token": f"example-access-{server.rotations}", "expires_in": 300,
                    "refresh_token": server.current, "refresh_expires_in": 0,
                    "token_type": "Bearer", "scope": _SCOPE,
                }
            server.rotated.set()
            if gated and not server.release.wait(5):
                return self.reply(503, {"error": "temporarily_unavailable"})
            self.reply(200, result)

    server = Server(("127.0.0.1", 0), Handler)
    server.origin = f"http://127.0.0.1:{server.server_address[1]}"
    server.failure = failure
    server.guard = threading.Lock()
    server.rotated, server.release = threading.Event(), threading.Event()
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.release.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _provider(root, origin, *, runtime="runtime-a", timeout=2):
    settings = Settings(base_url=origin, site_id="site-a", timeout_seconds=timeout,
        allow_insecure_http=True, cache_path=root / runtime / "tokens.json",
        credential_path=root / "data" / "credentials.json", use_cache=True, profile="default",
        identity_issuer=origin, oidc_scope=_SCOPE)
    transport = JsonTransport(base_url=origin, timeout_seconds=timeout)
    oidc = OidcClient(transport=transport, issuer_url=origin, client_id="sai-cli", scope=_SCOPE)
    return TokenProvider(settings=settings, transport=transport, environ={}, oidc_client=oidc)


def _seed_legacy(provider, token="example-refresh-0"):
    provider.credential_cache.put(provider._device_refresh_key(), token=token,
        expires_at=None, allow_unknown_expiry=True, scope=_SCOPE)


def _tokens(suffix="new"):
    return DeviceTokenResult(access_token="example-access-" + suffix,
        access_expires_at=int(time.time()) + 300, refresh_token="example-refresh-" + suffix,
        refresh_expires_at=None, scope=_SCOPE)


def _profile(root, provider):
    path = root / (provider.settings.cache_path.parent.name + ".toml")
    values = {"base_url": provider.settings.base_url, "identity_issuer": provider.settings.identity_issuer,
              "oidc_scope": _SCOPE, "site_id": "site-a", "cache_path": str(provider.settings.cache_path),
              "credential_path": str(provider.credential_cache.path),
              "timeout_seconds": provider.settings.timeout_seconds}
    path.write_text("[profiles.default]\n" + "".join(f"{key} = {json.dumps(value)}\n" for key, value in values.items()))
    path.chmod(0o600)
    return path


def _environment(root):
    return {"PATH": os.defpath, "NO_PROXY": "*", "PYTHONDONTWRITEBYTECODE": "1",
            "XDG_CONFIG_HOME": str(root / "config"), "XDG_DATA_HOME": str(root / "data"),
            "XDG_CACHE_HOME": str(root / "cache")}


@contextmanager
def _cli(root, profile, *, before_entry="", environment=None):
    entry = "import sys;sys.path.insert(0,sys.argv.pop(1));\n" + before_entry
    entry += "\nfrom sai_cli.cli import entrypoint;entrypoint()"
    process = subprocess.Popen([sys.executable, "-I", "-P", "-B", "-c", entry, _SOURCE,
        "auth", "status", "--config", str(profile)], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, env={**_environment(root), **(environment or {})}, start_new_session=True)
    try:
        yield process
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
        process.communicate(timeout=3)


def _wait_for(predicate, *, timeout=3):
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, "the synthetic operation did not reach its checkpoint"
        time.sleep(.01)


def test_session_survives_runtime_change_and_legacy_refresh_is_upgraded(tmp_path):
    with _issuer() as server:
        first = _provider(tmp_path, server.origin)
        _seed_legacy(first)
        lease = first.get()
        second = _provider(tmp_path, server.origin, runtime="runtime-b")
        assert second.get().token == lease.token
        assert second.device_refresh() == (server.current, None)
        assert second.device_scope() == _SCOPE
        assert server.rotations == server.token_calls == 1
        assert not first.settings.cache_path.exists() and not second.settings.cache_path.exists()


def test_legacy_runtime_access_cannot_restore_a_missing_device_session(tmp_path):
    with _issuer() as server:
        provider = _provider(tmp_path, server.origin)
        TokenCache(provider.settings.cache_path).put(provider._device_access_key(), token="example-obsolete-access",
                                                    expires_at=int(time.time()) + 300)
        with pytest.raises(AuthenticationError):
            provider.get()
        assert server.token_calls == 0


@pytest.mark.parametrize("legacy_state", ["valid", "malformed", "symlink"])
def test_unused_legacy_access_cannot_block_logout_or_restore_the_cleared_session(tmp_path, legacy_state):
    with _issuer() as server:
        provider = _provider(tmp_path, server.origin)
        provider.install_device_tokens(_tokens())
        legacy_path = provider.settings.cache_path
        TokenCache(legacy_path).put(provider._device_access_key(), token="example-obsolete-access",
                                   expires_at=int(time.time()) + 300)
        if legacy_state == "malformed":
            legacy_path.write_text("invalid legacy cache")
        elif legacy_state == "symlink":
            target = legacy_path.with_name("legacy-target.json")
            legacy_path.rename(target)
            legacy_path.symlink_to(target)
        legacy_bytes = legacy_path.read_bytes()
        assert provider.get().token == "example-access-new"
        assert provider.revoke_device() is True
        assert provider.device_refresh() is None
        for runtime in ("runtime-a", "runtime-b"):
            with pytest.raises(AuthenticationError):
                _provider(tmp_path, server.origin, runtime=runtime).get()
        assert legacy_path.read_bytes() == legacy_bytes
        assert legacy_path.is_symlink() == (legacy_state == "symlink")
        assert server.token_calls == 0


def test_access_refresh_and_scope_commit_as_one_protected_record(tmp_path, monkeypatch):
    with _issuer() as server:
        provider = _provider(tmp_path, server.origin)
        provider.install_device_tokens(_tokens("old"))
        before = provider.credential_cache.path.read_bytes()
        original = os.replace
        candidates = []

        def unavailable_commit(source, destination):
            if Path(destination) == provider.credential_cache.path:
                candidates.append(json.loads(Path(source).read_text())["entries"])
                raise OSError("synthetic storage failure")
            return original(source, destination)

        monkeypatch.setattr(os, "replace", unavailable_commit)
        with pytest.raises(AuthenticationError):
            provider.install_device_tokens(_tokens("new"))
        assert provider.credential_cache.path.read_bytes() == before
        assert provider.get().token == "example-access-old"
        assert provider.device_refresh()[0] == "example-refresh-old"
        assert len(candidates) == 1
        entries = candidates[0]
        assert entries[provider._device_access_key()]["token"] == "example-access-new"
        assert entries[provider._device_refresh_key()]["token"] == "example-refresh-new"
        assert {entry["scope"] for entry in entries.values()} == {_SCOPE}
        assert provider.credential_cache.path.stat().st_mode & 0o777 == 0o600
        assert provider.credential_cache.path.parent.stat().st_mode & 0o777 == 0o700


@pytest.mark.parametrize("failure", ["discovery-invalid", "discovery-unauthorized", "temporary", "client-config"])
def test_provider_or_transport_failure_preserves_the_existing_grant(tmp_path, failure):
    with _issuer(failure=failure) as server:
        provider = _provider(tmp_path, server.origin)
        _seed_legacy(provider)
        before = provider.credential_cache.path.read_bytes()
        with pytest.raises(SaiCliError) as caught:
            provider.get()
        assert caught.value.code != "credentials_unavailable"
        assert provider.credential_cache.path.read_bytes() == before
        assert server.rotations == 0
        server.failure = None
        assert _provider(tmp_path, server.origin).get().token == "example-access-1"
        assert server.rotations == 1


def test_failed_refresh_persistence_does_not_erase_the_previous_record(tmp_path, monkeypatch):
    with _issuer() as server:
        provider = _provider(tmp_path, server.origin)
        _seed_legacy(provider)
        before = provider.credential_cache.path.read_bytes()

        def unavailable(*args, **kwargs):
            raise AuthenticationError("the token cache could not be written")

        monkeypatch.setattr(provider.credential_cache, "_write", unavailable)
        with pytest.raises(AuthenticationError) as caught:
            provider.get()
        assert caught.value.code != "credentials_unavailable"
        assert provider.credential_cache.path.read_bytes() == before
        assert server.rotations == 1
        # The issuer consumed the old grant: local persistence failure is not a recovery guarantee.


def test_stale_access_rejection_does_not_invalidate_a_new_session(tmp_path):
    with _issuer() as server:
        provider = _provider(tmp_path, server.origin)
        provider.install_device_tokens(_tokens("old"))
        stale = provider.get()
        provider.install_device_tokens(_tokens("new"))
        provider.invalidate(stale)
        assert provider.get().token == "example-access-new"
        assert provider.device_refresh()[0] == "example-refresh-new"
        assert server.token_calls == 0


def test_rejected_refresh_cleanup_cannot_erase_a_subsequent_login(tmp_path, monkeypatch):
    with _issuer() as server:
        failing = _provider(tmp_path, server.origin)
        _seed_legacy(failing, "example-expired-grant")
        unlocked, installed = threading.Event(), threading.Event()
        original = failing._credential_lock

        @contextmanager
        def pause_after_unlock():
            try:
                with original():
                    yield
            finally:
                if not unlocked.is_set():
                    unlocked.set()
                    assert installed.wait(3)

        monkeypatch.setattr(failing, "_credential_lock", pause_after_unlock)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(failing.get)
            try:
                assert unlocked.wait(3)
                newer = _provider(tmp_path, server.origin)
                newer.install_device_tokens(_tokens("new"))
            finally:
                installed.set()
            with pytest.raises(AuthenticationError) as caught:
                future.result(timeout=3)
        assert caught.value.code == "credentials_unavailable"
        assert newer.get().token == "example-access-new"
        assert newer.device_refresh()[0] == "example-refresh-new"
        assert server.token_calls == 1 and server.rotations == 0


def test_rejected_existing_refresh_preserves_a_pending_permission_request(tmp_path):
    with _issuer() as server:
        provider = _provider(tmp_path, server.origin)
        _seed_legacy(provider, "example-expired-grant")
        requested_scope = _SCOPE + " sai.compute.read"
        provider.oidc_client.scope = requested_scope
        provider.store_pending_device_code(device_code="example-pending", expires_at=int(time.time()) + 300)
        pending = provider.pending_device_code()
        with pytest.raises(AuthenticationError) as caught:
            provider.get()
        assert caught.value.code == "credentials_unavailable"
        assert provider.device_refresh() is None
        resumed = _provider(tmp_path, server.origin)
        assert resumed.resume_device_authorization() == pending
        assert resumed.oidc_client.scope == requested_scope
        assert server.token_calls == 1 and server.rotations == 0


def test_explicit_logout_clears_the_session_and_pending_permission_request(tmp_path):
    with _issuer() as server:
        provider = _provider(tmp_path, server.origin)
        provider.install_device_tokens(_tokens())
        provider.store_pending_device_code(device_code="example-pending", expires_at=int(time.time()) + 300)
        assert provider.pending_device_code() is not None
        assert provider.revoke_device() is True
        assert provider.pending_device_code() is None
        assert provider.device_refresh() is None
        with pytest.raises(AuthenticationError):
            provider.get()
        assert server.token_calls == 0


@pytest.mark.skipif(os.name != "posix", reason="process-group and flock contract is qualified on Linux")
def test_parallel_cli_processes_share_one_refresh_across_runtime_paths(tmp_path):
    with _issuer(gated=True) as server:
        first = _provider(tmp_path, server.origin)
        second = _provider(tmp_path, server.origin, runtime="runtime-b")
        _seed_legacy(first)
        with _cli(tmp_path, _profile(tmp_path, first)) as left:
            assert server.rotated.wait(3)
            with _cli(tmp_path, _profile(tmp_path, second)) as right:
                server.release.set()
                for process in (left, right):
                    out, err = process.communicate(timeout=4)
                    assert process.returncode == 0, err
                    assert json.loads(out)["authenticated"] is True
        assert server.rotations == server.token_calls == 1
        assert server.business_calls == 2


@pytest.mark.skipif(os.name != "posix", reason="process-group and flock contract is qualified on Linux")
def test_waiting_for_credentials_is_bounded_and_does_not_delete_them(tmp_path):
    with _issuer() as server:
        provider = _provider(tmp_path, server.origin, timeout=.15)
        _seed_legacy(provider)
        before = provider.credential_cache.path.read_bytes()
        with provider._credential_lock(), _cli(tmp_path, _profile(tmp_path, provider)) as process:
            out, err = process.communicate(timeout=2)
            assert process.returncode == 6 and not out
            assert json.loads(err)["error"]["code"] == "credentials_busy"
        assert provider.credential_cache.path.read_bytes() == before
        assert server.token_calls == 0


_COMMIT_CHECKPOINT = """
import os, time
from pathlib import Path
original_replace = os.replace
def checkpoint_replace(source, destination):
    if str(destination) == os.environ['TEST_COMMIT_TARGET']:
        Path(os.environ['TEST_COMMIT_READY']).touch()
        deadline = time.monotonic() + 4
        while not Path(os.environ['TEST_COMMIT_RELEASE']).exists():
            if time.monotonic() >= deadline:
                raise RuntimeError('synthetic commit checkpoint timed out')
            time.sleep(.01)
    return original_replace(source, destination)
os.replace = checkpoint_replace
"""


@pytest.mark.skipif(os.name != "posix", reason="POSIX terminal signal contract")
@pytest.mark.parametrize("signum", [signal.SIGINT, signal.SIGTERM])
@pytest.mark.parametrize("phase", ["exchange", "commit"])
def test_terminal_cancel_finishes_rotation_before_exit(tmp_path, signum, phase):
    with _issuer(gated=phase == "exchange") as server:
        provider = _provider(tmp_path, server.origin)
        _seed_legacy(provider)
        ready, release = tmp_path / "commit-ready", tmp_path / "commit-release"
        environment = {"TEST_COMMIT_TARGET": str(provider.credential_cache.path),
                       "TEST_COMMIT_READY": str(ready), "TEST_COMMIT_RELEASE": str(release)}
        with _cli(tmp_path, _profile(tmp_path, provider), environment=environment,
                  before_entry=_COMMIT_CHECKPOINT if phase == "commit" else "") as process:
            _wait_for(server.rotated.is_set if phase == "exchange" else ready.exists)
            process.send_signal(signum)
            time.sleep(.05)
            assert process.poll() is None, "ordinary cancellation interrupted the credential transaction"
            server.release.set()
            release.touch()
            out, err = process.communicate(timeout=3)
            assert process.returncode == 128 + signum
            assert "example-access" not in out + err and "example-refresh" not in out + err
        assert provider.get().token == "example-access-1"
        assert provider.device_refresh()[0] == server.current
        assert server.token_calls == 1 and server.business_calls == 0


@pytest.mark.skipif(os.name != "posix", reason="POSIX terminal signal contract")
def test_tui_cancellation_waits_for_an_inflight_rotation_and_reaps_child(tmp_path, monkeypatch):
    with _issuer(gated=True) as server:
        provider = _provider(tmp_path, server.origin, timeout=2)
        _seed_legacy(provider)
        args = build_parser().parse_args(["tui", "--config", str(_profile(tmp_path, provider))])
        queries = Queries(args, _environment(tmp_path))
        children = []
        original = asyncio.create_subprocess_exec

        async def capture(*args, **kwargs):
            child = await original(*args, **kwargs)
            children.append(child)
            return child

        monkeypatch.setattr(asyncio, "create_subprocess_exec", capture)

        async def run():
            task = asyncio.create_task(queries._command(["auth", "status"], remote=True))
            try:
                assert await asyncio.to_thread(server.rotated.wait, 3)
                task.cancel()
                await asyncio.sleep(1.15)
                assert not task.done(), "TUI killed the credential update after the old one-second grace"
                server.release.set()
                with pytest.raises(asyncio.CancelledError):
                    await asyncio.wait_for(task, 3)
            finally:
                server.release.set()
                if not task.done():
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)

        asyncio.run(run())
        assert len(children) == 1 and children[0].returncode is not None
        assert provider.get().token == "example-access-1"
        assert server.token_calls == 1 and server.business_calls == 0


@pytest.mark.skipif(os.name != "posix", reason="POSIX terminal signal contract")
def test_native_tui_cancel_stays_prompt_without_loading_remote_settings(tmp_path, monkeypatch):
    ready = tmp_path / "native-ready"
    binary = tmp_path / "squeue"
    binary.write_text(f"#!{sys.executable}\nfrom pathlib import Path\nimport time\n"
                      f"Path({str(ready)!r}).touch()\ntime.sleep(10)\n")
    binary.chmod(0o755)
    queries = Queries(build_parser().parse_args(["tui"]), {**_environment(tmp_path), "PATH": str(tmp_path)})

    def no_remote_settings():
        pytest.fail("native cancellation loaded remote settings")

    monkeypatch.setattr(queries, "settings", no_remote_settings)

    async def run():
        task = asyncio.create_task(queries._command(["jobs", "local"]))
        try:
            deadline = time.monotonic() + 3
            while not ready.exists():
                assert time.monotonic() < deadline
                await asyncio.sleep(.01)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, 1.5)
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    asyncio.run(run())
