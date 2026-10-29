"""Explicit terminal authorization uses the real CLI and returns to the selected query."""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
import json
import os
from pathlib import Path
import select
import signal
import struct
import subprocess
import sys
import threading
import time

import pytest

from sai_cli.cli import build_parser
from sai_cli.errors import ConfigError
from sai_cli.tui_queries import Queries
from test_cli_auth import _AuthHandler, _server
from test_default_account import state
from test_local_jobs import native_client, native_job
from test_overview import sample
from test_recovery_actions import _environment, _profile, _run, _selection
from test_site_transport import http_endpoint


pytestmark = pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux PTY and child-process acceptance")
_SOURCE = Path(__file__).resolve().parents[1] / "src"

# Observe the real app and processes; all decisions and auth exchanges remain production code.
_OBSERVE = r'''
import json, os, sys
from pathlib import Path
sys.path.insert(0, sys.argv.pop(1))
from sai_cli.tui import QueryApp
from sai_cli.tui_queries import Queries
events = Path(os.environ['TEST_EVENTS'])
children = []
def record(event, **values):
    with events.open('a') as handle:
        handle.write(json.dumps({'event': event, **values}) + '\n')
original_spawn = Queries._spawn
async def spawn(self, arguments):
    process = await original_spawn(self, arguments)
    children.append(process)
    record('child', pid=process.pid, login=arguments[:2] == ['auth', 'login'])
    return process
Queries._spawn = spawn
original_authorize = Queries.authorize
async def authorize(self, argv):
    record('authorize', readers_alive=[child.pid for child in children if child.returncode is None])
    return await original_authorize(self, argv)
Queries.authorize = authorize
original_failure = QueryApp._show_failure
injected = False
def failure(self, request, error, *, directory_ready):
    global injected
    if not injected and 'TEST_RECOVERY' in os.environ:
        error.recovery_argv = tuple(json.loads(os.environ['TEST_RECOVERY']))
        injected = True
    original_failure(self, request, error, directory_ready=directory_ready)
    record('error', code=getattr(error, 'code', None), request_id=getattr(error, 'request_id', None),
           view=self.view, selection=self.selection, can_authorize=self._can_authorize(self._recovery_error),
           snapshot=self.snapshot is not None, authorizing=self._authorizing)
QueryApp._show_failure = failure
original_render = QueryApp._render
def render(self):
    original_render(self)
    if self.snapshot is not None:
        record('loaded', view=self.view, selection=self.selection, authorizing=self._authorizing)
QueryApp._render = render
from sai_cli.cli import entrypoint
entrypoint()
'''


class _Terminal:
    def __init__(self, process, master, slave, events, before):
        self.process, self.master, self.slave = process, master, slave
        self.events, self.before = events, before
        self.output = bytearray()
        self.extra_children = []

    def rows(self, event=None):
        if not self.events.exists():
            return []
        lines = self.events.read_text().splitlines()
        rows = [json.loads(line) for line in lines]
        return rows if event is None else [row for row in rows if row["event"] == event]

    def drain(self):
        if select.select([self.master], [], [], .02)[0]:
            try:
                self.output.extend(os.read(self.master, 16384))
                del self.output[:-131072]
            except OSError:
                pass

    def wait(self, condition, timeout=5):
        deadline = time.monotonic() + timeout
        while not condition():
            assert self.process.poll() is None, bytes(self.output).decode(errors="replace")
            assert time.monotonic() < deadline, self.rows()
            self.drain()

    def press(self, key):
        os.write(self.master, key.encode())

    def quit(self):
        import termios
        self.press("q")
        deadline = time.monotonic() + 5
        while self.process.poll() is None:
            assert time.monotonic() < deadline, self.rows()
            self.drain()
        self.drain()
        assert self.process.returncode == 0, bytes(self.output).decode(errors="replace")
        assert termios.tcgetattr(self.slave) == self.before
        assert "opaque-access-token" not in self.output.decode(errors="replace")
        for pid in [row["pid"] for row in self.rows("child")] + self.extra_children:
            assert not Path(f"/proc/{pid}").exists(), f"Child {pid} survived terminal exit"


@contextmanager
def _terminal(tmp_path, env, profile, *, recovery=None, initial="account"):
    import fcntl
    import pty
    import termios

    master, slave = pty.openpty()
    before = termios.tcgetattr(slave)
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 100, 0, 0))
    events = tmp_path / "terminal-events.jsonl"
    process_env = {**env, "TEST_EVENTS": str(events), "TERM": "xterm-256color", "LANG": "C.UTF-8"}
    if recovery is not None:
        process_env["TEST_RECOVERY"] = json.dumps(recovery)
    process = subprocess.Popen([sys.executable, "-I", "-P", "-B", "-c", _OBSERVE, str(_SOURCE),
        "tui", "--view", initial, "--account", "org-research", *_selection(profile)],
        stdin=slave, stdout=slave, stderr=slave, env=process_env, start_new_session=True, cwd=tmp_path)
    terminal = _Terminal(process, master, slave, events, before)
    try:
        yield terminal
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=3)
        for child in terminal.rows("child"):
            try:
                os.killpg(child["pid"], signal.SIGKILL)
            except ProcessLookupError:
                pass
        os.close(master)
        os.close(slave)


def _overview():
    value = sample()
    value["context"].update(slurm_account="org-research", canonical_account="org-research",
                            default_account="org-research", label="Research")
    return value


def test_l_authorizes_then_refreshes_the_same_account_and_q_restores_the_terminal(tmp_path):
    env = _environment(tmp_path)
    deny = threading.Event()
    with _server() as (issuer, server):
        def reply(call, _):
            assert call["method"] == "GET"
            if "/defaults?" in call["path"]:
                return 200, state()
            token = call["bearer"].removeprefix("Bearer ")
            if deny.is_set() and "sai.billing.read" not in server.access_scopes.get(token, set()):
                return 403, {"detail": {"code": "identity_scope_denied"}}
            return 200, _overview()

        with http_endpoint(reply) as (origin, calls):
            profile = _profile(tmp_path, origin, issuer=issuer, baseline="openid offline_access sai.compute.read")
            _run(["sai", "auth", "login", *_selection(profile)], env, cwd=tmp_path)
            with _terminal(tmp_path, env, profile) as terminal:
                terminal.wait(lambda: bool(terminal.rows("loaded")))
                initial = terminal.rows("loaded")[-1]
                assert (initial["view"], initial["selection"]) == ("account", "org-research")
                deny.set()
                terminal.press("r")
                terminal.wait(lambda: bool(terminal.rows("error")))
                error = terminal.rows("error")[-1]
                assert error["code"] == "identity_scope_denied" and error["can_authorize"]
                assert error["selection"] == "org-research"
                assert sum(row["path"] == "/oauth/device" for row in server.requests) == 1
                before = len(terminal.rows("loaded"))
                server.token_suffix = "-additional"
                terminal.press("l")
                terminal.wait(lambda: len(terminal.rows("loaded")) > before)
                restored = terminal.rows("loaded")[-1]
                assert (restored["view"], restored["selection"]) == (initial["view"], initial["selection"])
                assert not restored["authorizing"]
                assert terminal.rows("authorize") == [{"event": "authorize", "readers_alive": []}]
                assert sum(row["login"] for row in terminal.rows("child")) == 1
                assert "sai.billing.read" in server.requested_scope.split()
                assert b"ABCD-EFGH" in terminal.output
                assert "slurm_account_name=org-research" in calls[-1]["path"]
                terminal.quit()


def test_authorization_waits_until_an_obsolete_native_read_and_its_child_are_reaped(tmp_path, native_client):
    native_env, _, _ = native_client
    env = _environment(tmp_path)
    env.update(PATH=str(tmp_path) + os.pathsep + env["PATH"], NATIVE_SCENARIO="timeout",
               NATIVE_CALL=native_env["NATIVE_CALL"], NATIVE_PAYLOAD=native_env["NATIVE_PAYLOAD"])
    with _server() as (issuer, _), http_endpoint(
        lambda call, _: (200, state() if "/defaults?" in call["path"] else _overview())
    ) as (origin, _):
        profile = _profile(tmp_path, origin, issuer=issuer,
                           baseline="openid offline_access sai.compute.read sai.billing.read")
        with _terminal(tmp_path, env, profile, initial="jobs") as terminal:
            terminal.wait(lambda: Path(native_env["NATIVE_CALL"]).exists())
            native_pid = terminal.rows("child")[0]["pid"]
            children = Path(f"/proc/{native_pid}/task/{native_pid}/children")
            terminal.extra_children = [int(value) for value in children.read_text().split()]
            assert terminal.extra_children
            terminal.press("5")
            terminal.wait(lambda: bool(terminal.rows("error")))
            assert terminal.rows("error")[-1]["can_authorize"]
            assert Path(f"/proc/{native_pid}").exists()
            terminal.press("l")
            terminal.wait(lambda: bool(terminal.rows("loaded")))
            assert terminal.rows("authorize") == [{"event": "authorize", "readers_alive": []}]
            assert not Path(f"/proc/{native_pid}").exists()
            assert terminal.rows("loaded")[-1]["view"] == "account"
            terminal.quit()


@pytest.mark.parametrize("mode", ["failure", "cancel"])
def test_failed_or_interrupted_login_returns_to_tui_without_success(tmp_path, monkeypatch, mode):
    env = _environment(tmp_path)
    token_requested, deny = threading.Event(), threading.Event()
    original = _AuthHandler.do_POST

    def token_result(handler):
        if handler.path != "/oauth/token" or not deny.is_set():
            return original(handler)
        handler.rfile.read(int(handler.headers.get("Content-Length", "0")))
        handler.server.requests.append({"path": handler.path})
        if mode == "failure":
            handler._json({"detail": {"code": "identity_temporarily_unavailable", "message": "Identity temporarily unavailable"}}, 503)
        else:
            handler._json({"error": "authorization_pending"}, 400)
        token_requested.set()

    monkeypatch.setattr(_AuthHandler, "do_POST", token_result)
    with _server() as (issuer, _):
        def reply(call, _):
            if "/defaults?" in call["path"]:
                return 200, state()
            if deny.is_set():
                return 403, {"detail": {"code": "identity_scope_denied"}}
            return 200, _overview()

        with http_endpoint(reply) as (origin, calls):
            profile = _profile(tmp_path, origin, issuer=issuer, baseline="openid offline_access sai.compute.read")
            _run(["sai", "auth", "login", *_selection(profile)], env, cwd=tmp_path)
            with _terminal(tmp_path, env, profile) as terminal:
                terminal.wait(lambda: bool(terminal.rows("loaded")))
                deny.set()
                terminal.press("r")
                terminal.wait(lambda: bool(terminal.rows("error")))
                initial = terminal.rows("error")[-1]
                assert initial["can_authorize"] and initial["selection"] == "org-research"
                loaded_before, calls_before = len(terminal.rows("loaded")), len(calls)
                terminal.press("l")
                terminal.wait(token_requested.is_set)
                if mode == "cancel":
                    os.kill(terminal.process.pid, signal.SIGINT)
                terminal.wait(lambda: len(terminal.rows("error")) >= 2)
                failure = terminal.rows("error")[-1]
                assert failure["code"] == ("interrupted" if mode == "cancel" else "identity_temporarily_unavailable")
                assert (failure["view"], failure["selection"]) == (initial["view"], initial["selection"])
                assert not failure["snapshot"] and not failure["authorizing"]
                assert len(terminal.rows("loaded")) == loaded_before and len(calls) == calls_before
                assert failure["can_authorize"]
                if mode == "failure":
                    assert failure["request_id"] == "auth-request"
                terminal.quit()


@pytest.mark.parametrize("recovery", [
    ("sai", "unknown-action"),
    ("sai", "account", "set-default", "account-research", "--if-current", "auto", "--request-id", "request-example"),
    ("sai", "configure", "SERVICE_URL"),
])
def test_l_never_executes_an_unknown_business_write_or_configuration_action(tmp_path, recovery):
    env = _environment(tmp_path)
    with _server() as (origin, server):
        profile = _profile(tmp_path, origin)
        with _terminal(tmp_path, env, profile, recovery=recovery) as terminal:
            terminal.wait(lambda: bool(terminal.rows("error")))
            assert not terminal.rows("error")[-1]["can_authorize"]
            child_count = len(terminal.rows("child"))
            terminal.press("l")
            deadline = time.monotonic() + .25
            while time.monotonic() < deadline:
                terminal.drain()
            assert not terminal.rows("authorize") and not server.requests
            assert len(terminal.rows("child")) == child_count
            assert not any(row["login"] for row in terminal.rows("child"))
            terminal.quit()
        queries = Queries(build_parser().parse_args(["tui", *_selection(profile)]), env)
        with pytest.raises(ConfigError):
            asyncio.run(queries.authorize(recovery))
        assert not server.requests


def test_pending_device_request_is_not_reported_as_completed_authorization(tmp_path):
    env = _environment(tmp_path)
    with _server() as (origin, server):
        profile = _profile(tmp_path, origin)
        recovery = ("sai", "auth", "login", "--no-wait", *_selection(profile))
        with _terminal(tmp_path, env, profile, recovery=recovery) as terminal:
            terminal.wait(lambda: bool(terminal.rows("error")))
            assert terminal.rows("error")[-1]["can_authorize"]
            terminal.press("l")
            terminal.wait(lambda: len(terminal.rows("error")) >= 2)
            failure = terminal.rows("error")[-1]
            assert failure["code"] == "contract_invalid"
            assert not terminal.rows("loaded") and not failure["snapshot"]
            assert not failure["authorizing"]
            assert any(row["path"] == "/oauth/device" for row in server.requests)
            assert not any(row["path"] == "/oauth/token" for row in server.requests)
            terminal.quit()
