from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from io import StringIO
import json
import os
from pathlib import Path
import pwd
import subprocess
import sys

import pytest

from sai_cli.cli import main
from sai_cli.local_jobs import _item


def number(value, *, present=True, infinite=False):
    return {"set": present, "infinite": infinite, "number": value}


@pytest.fixture
def native_job():
    return {
        "job_id": 42, "array_job_id": number(0), "array_task_id": number(0, present=False),
        "array_task_string": "", "name": "simulation", "user_name": pwd.getpwuid(os.geteuid()).pw_name,
        "account": "research", "job_state": ["RUNNING"], "priority": number(100),
        "partition": "gpu-standard", "qos": "normal", "node_count": number(2),
        "cpus": number(16), "tasks": number(8), "nodes": "compute-[a,b]", "state_reason": "None",
        "submit_time": number(1790000000), "start_time": number(1790000020),
        "end_time": number(1890000000), "suspend_time": number(0), "pre_sus_time": number(0),
        "tres_per_node": "gres/gpu:example:2", "memory_per_tres": "gpu:15360",
        "memory_per_cpu": number(0, present=False), "memory_per_node": number(15360),
        "command": "private executable", "environment": ["PRIVATE=value"],
        "standard_output": "/private/output", "current_working_directory": "/private/work",
    }


@pytest.fixture
def native_client(tmp_path, native_job):
    binary = tmp_path / "squeue"
    binary.write_text(f"#!{sys.executable}\n" + '''
import json, os, sys, time
from pathlib import Path
Path(os.environ["NATIVE_CALL"]).write_text(json.dumps({
    "argv": sys.argv[1:], "uid": os.geteuid(), "stdin_eof": sys.stdin.read() == "",
    "sai_token_present": "SAI_TOKEN" in os.environ,
    "squeue_users_present": "SQUEUE_USERS" in os.environ,
    "slurm_conf": os.environ.get("SLURM_CONF"),
}))
mode = os.environ.get("NATIVE_SCENARIO", "valid")
if mode == "timeout":
    time.sleep(5)
elif mode == "failure":
    print("provider-private-detail", file=sys.stderr)
    raise SystemExit(1)
elif mode == "oversize":
    sys.stdout.write("x" * 1000000)
elif mode == "malformed":
    print("provider-private-detail")
else:
    print(Path(os.environ["NATIVE_PAYLOAD"]).read_text())
''')
    binary.chmod(0o755)
    payload_path = tmp_path / "payload.json"
    payload = {"meta": {"slurm": {"cluster": "cluster-a"}}, "errors": [], "warnings": [], "jobs": [native_job]}
    payload_path.write_text(json.dumps(payload))
    env = {"PATH": str(tmp_path), "NATIVE_PAYLOAD": str(payload_path), "NATIVE_CALL": str(tmp_path / "called.json"),
           "SAI_MANAGED_LOGIN_NODE": "1", "SAI_CONFIG": str(tmp_path / "absent-config"),
           "SAI_TOKEN": "test-token", "SAI_BASE_URL": "http://invalid.invalid", "SQUEUE_USERS": "someone-else",
           "USER": "someone-else", "LOGNAME": "someone-else", "SLURM_CONF": "native-slurm.conf"}
    return env, payload_path, payload


def invoke(env, *args):
    output, errors = StringIO(), StringIO()
    code = main(list(args), environ=env, stdout=output, stderr=errors)
    return code, output.getvalue(), errors.getvalue()


def test_local_read_has_no_http_config_or_auth_dependency(native_client, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("local read reached the remote stack")
    monkeypatch.setattr("sai_cli.config.resolve_settings", forbidden)
    monkeypatch.setattr("sai_cli.cli._build_transport", forbidden)
    monkeypatch.setattr("sai_cli.cli._build_oidc_client", forbidden)
    env, _, _ = native_client
    code, output, errors = invoke(env, "jobs", "local")
    assert code == 0 and not errors
    result = json.loads(output)
    who = pwd.getpwuid(os.geteuid()).pw_name
    assert result["actor"] == {"uid": os.geteuid(), "user": who}
    assert result["authority"] == "native" and result["schema_version"] == "native.jobs/v1"
    assert result["filters"]["users"] == who
    call = json.loads(Path(env["NATIVE_CALL"]).read_text())
    assert call["argv"] == ["--json", "--local", f"--user={who}"]
    assert call["stdin_eof"] and call["uid"] == os.geteuid()
    assert not call["sai_token_present"] and not call["squeue_users_present"]
    assert call["slurm_conf"] == "native-slurm.conf"
    assert "private" not in output and "environment" not in output


def test_local_startup_does_not_load_remote_auth_transport_or_other_product_modules(native_client):
    env, _, _ = native_client
    program = '''
import io, json, sys
from sai_cli.cli import main
output, errors = io.StringIO(), io.StringIO()
assert main(['jobs', 'local'], stdout=output, stderr=errors) == 0, errors.getvalue()
assert json.loads(output.getvalue())['authority'] == 'native'
remote = {'sai_cli.auth', 'sai_cli.config', 'sai_cli.client', 'sai_cli.transport',
          'sai_cli.overview_view', 'sai_cli.storage_summary', 'sai_cli.site_jobs', 'http.client', 'ssl'}
assert not remote.intersection(sys.modules), sorted(remote.intersection(sys.modules))
'''
    completed = subprocess.run([sys.executable, '-c', program],
                               env={**os.environ, **env}, capture_output=True, text=True, timeout=5)
    assert completed.returncode == 0, completed.stderr


@pytest.mark.parametrize("arguments,expected", [
    (["-A", "research"], ["--account=research"]),
    (["--accounts", "research,other", "-q", "normal"], ["--account=research,other", "--qos=normal"]),
    (["-p", "gpu-standard", "-t", "PD,R"], ["--partition=gpu-standard", "--states=PD,R"]),
    (["--user", "*"], []),
    (["-u", "alice", "-A", "research"], ["--user=alice", "--account=research"]),
    (["--status", "ST"], ["--states=ST"]),
])
def test_native_alias_filter_semantics(native_client, arguments, expected):
    env, _, _ = native_client
    assert invoke(env, "jobs", "local", *arguments)[0] == 0
    call = json.loads(Path(env["NATIVE_CALL"]).read_text())
    assert call["argv"] == ["--json", "--local", *expected]


def test_arguments_are_data_not_shell_source(native_client, tmp_path):
    env, _, _ = native_client
    marker = tmp_path / "must-not-exist"
    value = f"research; touch {marker}"
    assert invoke(env, "jobs", "local", "-A", value)[0] == 0
    assert not marker.exists()
    assert json.loads(Path(env["NATIVE_CALL"]).read_text())["argv"][-1] == "--account=" + value


@pytest.mark.parametrize("options", [["--timeout", "1", "jobs", "local"], ["jobs", "local", "--timeout", "1"]])
def test_native_timeout_supported_before_command_and_after_leaf(native_client, options):
    assert invoke(native_client[0], *options)[0] == 0


@pytest.mark.parametrize("options", [
    ["--site", "site-b", "jobs", "local"], ["--base-url", "https://example.invalid", "jobs", "local"],
    ["--profile", "remote", "jobs", "local"], ["--cluster", "cluster-b", "jobs", "local"],
    ["jobs", "local", "--timeout", "nan"], ["jobs", "local", "--timeout", "0"],
    ["jobs", "local", "--limit", "0"], ["jobs", "local", "-u", ""], ["jobs", "local", "-A", "bad\nvalue"],
])
def test_conflicting_or_invalid_intent_fails_before_native_execution(native_client, options):
    env, _, _ = native_client
    code, output, errors = invoke(env, *options)
    assert code == 2 and not output and json.loads(errors)["error"]["code"] == "configuration_invalid"
    assert not Path(env["NATIVE_CALL"]).exists()


@pytest.mark.parametrize("mode,expected_code,exit_code", [
    ("failure", "native_query_failed", 6), ("malformed", "native_response_invalid", 7),
    ("timeout", "native_query_timeout", 6), ("oversize", "native_response_too_large", 6),
])
def test_native_failures_never_become_empty_success_or_leak_stderr(native_client, monkeypatch, mode, expected_code, exit_code):
    env, _, _ = native_client
    env["NATIVE_SCENARIO"] = mode
    monkeypatch.setattr("sai_cli.native_process.MAX_NATIVE_BYTES", 65536)
    code, output, errors = invoke(env, "jobs", "local", "--timeout", "0.1" if mode == "timeout" else "2")
    assert code == exit_code and not output
    assert json.loads(errors)["error"]["code"] == expected_code
    assert "provider-private-detail" not in errors


def test_missing_native_client_does_not_contact_portal(native_client):
    env, _, _ = native_client
    Path(env["PATH"], "squeue").unlink()
    code, output, errors = invoke(env, "jobs", "local")
    assert code == 6 and not output
    assert json.loads(errors)["error"]["code"] == "native_client_unavailable"


@pytest.mark.parametrize("invalid", [True, -1, "12", {"set": "yes", "infinite": False, "number": 2}])
def test_malformed_row_is_not_silently_dropped(native_client, invalid):
    env, path, payload = native_client
    bad = deepcopy(payload["jobs"][0])
    bad["cpus"] = invalid
    payload["jobs"].append(bad)
    path.write_text(json.dumps(payload))
    code, output, errors = invoke(env, "jobs", "local")
    assert code == 7 and not output and json.loads(errors)["error"]["code"] == "native_response_invalid"


def test_empty_native_queue_is_success_only_when_source_has_no_errors(native_client):
    env, path, payload = native_client
    payload["jobs"] = []
    path.write_text(json.dumps(payload))
    code, output, errors = invoke(env, "jobs", "local")
    assert code == 0 and not errors and json.loads(output)["items"] == []
    payload["errors"] = [{"description": "provider-private-detail"}]
    path.write_text(json.dumps(payload))
    code, output, errors = invoke(env, "jobs", "local")
    assert code == 6 and not output and "provider-private-detail" not in errors


def test_native_array_zero_pending_forecast_and_suspension(native_job):
    native_job.update(array_job_id=number(40), array_task_id=number(0))
    assert _item(native_job, observed=1790000120).canonical_id == "40_0"
    native_job.update(job_state=["PENDING"], start_time=number(1890000000))
    pending = _item(native_job, observed=1790000120).values
    assert pending["start_time"] is None and pending["elapsed_seconds"] is None
    assert pending["run_wait_seconds"] == 120 and pending["slots"] == 8
    native_job.update(job_state=["SUSPENDED"], start_time=number(1790000020),
                      suspend_time=number(1790000060), pre_sus_time=number(40))
    assert _item(native_job, observed=1790000120).values["elapsed_seconds"] == 40
    native_job["job_state"] = ["RUNNING"]
    assert _item(native_job, observed=1790000120).values["elapsed_seconds"] == 100


def test_native_resource_units_and_unknown_values(native_job):
    row = _item(native_job, observed=1790000120).values
    assert row["mem_per_unit"] == "15G/GPU" and row["gpus_per_node"] == 2
    native_job.update(tres_per_node="gres/gpu:type-a:2,gres/gpu:type-b:1", memory_per_tres="")
    assert _item(native_job, observed=1790000120).values["gpus_per_node"] == 3
    native_job["tres_per_node"] = "gres/gpu:3,gres/gpu:type-a:2,gres/gpu:type-b:1"
    assert _item(native_job, observed=1790000120).values["gpus_per_node"] == 3
    native_job.update(tres_per_node="gres/mps:100", cpus=number(0, present=False),
                      memory_per_node=number(0, infinite=True), account=None, user_name=None)
    row = _item(native_job, observed=1790000120).values
    assert row["gpus_per_node"] is None and row["mem_per_unit"] is None and row["slots"] is None
    assert row["slurm_account"] is None and row["slurm_user"] is None


def test_human_and_json_share_projection_without_terminal_control_sequences(native_client):
    env, path, payload = native_client
    payload["jobs"][0].update(job_state=["STOPPED"], name="long-name\x1b[31m\nnext")
    path.write_text(json.dumps(payload))
    code, raw, _ = invoke(env, "jobs", "local")
    code_table, table, errors = invoke(env, "jobs", "local", "--format", "table")
    assert code == code_table == 0 and not errors
    row = json.loads(raw)["items"][0]
    assert row["state"] == "STOPPED" and "\\x1b" in row["name"]
    assert "\x1b" not in table and "STOPPED" in table and "simulation" not in table
    local_start = datetime.fromisoformat(row['start_time']).astimezone().strftime('%Y-%m-%d %H:%M:%S')
    assert local_start in table and row['start_time'].endswith('Z')


def test_explicit_limit_is_reported_not_a_complete_queue(native_client):
    env, path, payload = native_client
    second = deepcopy(payload["jobs"][0])
    second["job_id"] = 43
    payload["jobs"].append(second)
    path.write_text(json.dumps(payload))
    code, raw, _ = invoke(env, "jobs", "local", "--limit", "1")
    assert code == 0 and json.loads(raw)["has_more"] and json.loads(raw)["count"] == 1
    assert "More jobs matched" in invoke(env, "jobs", "local", "--limit", "1", "--format", "table")[1]
