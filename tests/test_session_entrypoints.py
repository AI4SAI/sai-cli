"""The shipped login fragment and real terminal exit preserve an in-flight session."""
import os
from pathlib import Path
import select
import signal
import struct
import subprocess
import sys
import time

import pytest

from test_session_lifecycle import _environment, _issuer, _profile, _provider, _seed_legacy


SOURCE = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(os.name != "posix", reason="shared Bash and POSIX terminal entrypoints")


def test_real_login_timeout_finishes_refresh_then_returns_to_shell(tmp_path):
    with _issuer(gated=True) as server:
        provider = _provider(tmp_path, server.origin, timeout=3)
        _seed_legacy(provider)
        profile = _profile(tmp_path, provider)
        wrapper = tmp_path / "sai"
        wrapper.write_text(f"#!{sys.executable}\nimport sys,time\nsys.path.insert(0,{str(SOURCE / 'src')!r})\n"
                           f"sys.argv[1:1]=['--config',{str(profile)!r}]\ntime.sleep(3.2)\n"
                           "from sai_cli.cli import entrypoint\nentrypoint()\n")
        wrapper.chmod(0o755)
        for name in ("aliases.txt", "rules.bash", "status.bash", "notes.bash"):
            (tmp_path / name).write_text("")
        fragment = tmp_path / "login.bash"
        fragment.write_text((SOURCE / "site/shell/login_summary.bash").read_text()
                            .replace("/opt/sai/bin/sai", str(wrapper)).replace("/opt/sai/shell", str(tmp_path)))
        process = subprocess.Popen(["bash", "--noprofile", "--norc", "-ilc",
            '_SAI_LOGIN_ACCOUNT=org-example; source "$1"; printf "SHELL-READY\\n"', "bash", str(fragment)],
            env={**_environment(tmp_path), "HOSTNAME": "login-example"}, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, start_new_session=True, cwd=tmp_path)
        started = time.monotonic()
        try:
            assert server.rotated.wait(5)
            time.sleep(max(0, started + 5.25 - time.monotonic()))
            assert process.poll() is None
            server.release.set()
            stdout, stderr = process.communicate(timeout=4)
            elapsed = time.monotonic() - started
            assert process.returncode == 0
            assert 5 <= elapsed < 9
            assert "SHELL-READY" in stdout and "Slurm Account  org-example" in stdout
            assert "当前目录" in stdout and "读取超时" in stderr
            assert _provider(tmp_path, server.origin).get().token == "example-access-1"
            assert server.rotations == 1 and server.business_calls == 0
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
            process.communicate(timeout=3)


def test_real_tui_q_restores_terminal_and_preserves_rotated_session(tmp_path):
    import fcntl
    import pty
    import termios

    with _issuer(gated=True) as server:
        provider = _provider(tmp_path, server.origin, timeout=3)
        _seed_legacy(provider)
        profile = _profile(tmp_path, provider)
        master, slave = pty.openpty()
        before = termios.tcgetattr(slave)
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 0, 0))
        entry = "import sys;sys.path.insert(0,sys.argv.pop(1));from sai_cli.cli import entrypoint;entrypoint()"
        process = subprocess.Popen([sys.executable, "-I", "-P", "-B", "-c", entry, str(SOURCE / "src"),
            "tui", "--view", "account", "--config", str(profile)], stdin=slave, stdout=slave, stderr=slave,
            env={**_environment(tmp_path), "TERM": "xterm-256color", "LANG": "C.UTF-8"}, start_new_session=True)

        def drain():
            if select.select([master], [], [], .01)[0]:
                os.read(master, 8192)

        try:
            deadline = time.monotonic() + 5
            while not server.rotated.is_set():
                assert time.monotonic() < deadline and process.poll() is None
                drain()
            started = time.monotonic()
            os.write(master, b"q")
            while time.monotonic() - started < 1.15:
                drain()
            assert process.poll() is None
            server.release.set()
            deadline = time.monotonic() + 4
            while process.poll() is None:
                assert time.monotonic() < deadline
                drain()
            assert process.returncode == 0
            assert time.monotonic() - started < 4
            assert termios.tcgetattr(slave) == before
            assert _provider(tmp_path, server.origin).get().token == "example-access-1"
            assert server.rotations == 1 and server.business_calls == 0
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=3)
            os.close(master)
            os.close(slave)
