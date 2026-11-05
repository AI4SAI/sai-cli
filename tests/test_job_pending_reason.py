"""Native waiting reasons retain separate optional SAI account context."""
import asyncio
from copy import deepcopy
from html import unescape
import json
import os
from pathlib import Path
import sys
import time

import pytest

from sai_cli.cli import build_parser
from sai_cli.contracts import JobItem
from sai_cli.errors import ContractError
from sai_cli.job_reasons import job_reason
from sai_cli.tui import QueryApp
from sai_cli.tui_queries import Queries
from sai_compute_restrictions import read_snapshot
from test_local_jobs import native_client, native_job, invoke
from test_native_topology import topology_client
from test_site_transport import http_endpoint, issuer, profile, invoke as invoke_remote, site_payload
from test_tui import loaded


@pytest.fixture
def account_snapshot(tmp_path, monkeypatch):
    root = tmp_path / "admission"
    root.mkdir(mode=0o755)
    path = root / "cluster-a.json"
    published = int(time.time())
    value = {"schema_version": "sai.compute-restrictions/v1", "cluster_id": "cluster-a",
        "generation": time.time_ns() // 1000, "published_at": published, "expires_at": published + 300, "accounts": {
            "org-parent": {"lineage": ["org-parent"], "group_jobs_limit": 0, "reason": "arrears", "observed_at": 1790000000},
            "research": {"lineage": ["org-parent", "research"], "group_jobs_limit": None, "observed_at": 1790000000}}}
    path.write_text(json.dumps(value))
    path.chmod(0o644)
    calls = []
    def read(*, cluster):
        calls.append(cluster)
        return read_snapshot(cluster=cluster, root=root, trusted_uids=(os.getuid(),))
    monkeypatch.setattr("sai_cli.local_jobs.read_snapshot", read)
    return path, value, calls


@pytest.mark.parametrize("code,label", [
    ("arrears", "欠费"), ("severe_arrears", "严重欠费"),
    ("no_compute_funding", "资金不足"), ("admin_blocked", "管理停用"),
])
def test_native_queue_and_exact_detail_keep_separate_account_context(topology_client, account_snapshot, code, label):
    env, path, payload = topology_client
    snapshot_path, snapshot, reads = account_snapshot
    snapshot["accounts"]["org-parent"]["reason"] = code
    snapshot_path.write_text(json.dumps(snapshot))
    job = payload["jobs"][0]
    job.update(job_state=["PENDING"], state_reason="AssocGrpJobsLimit",
               state_description="Arrears: ignored-account")
    path.write_text(json.dumps(payload))
    rc, output, error = invoke(env, "jobs", "local")
    assert rc == 0, error
    row = json.loads(output)["items"][0]
    assert row["reason_or_nodelist"] == "AssocGrpJobsLimit"
    assert row["account_restriction"] == {"code": code, "account": "org-parent",
        "source": "sai_applied_policy", "observed_at": 1790000000}
    assert "pending_reason" not in row
    assert row["slurm_account"] == "research"
    assert json.loads(Path(env["NATIVE_CALL"]).read_text())["argv"][0:2] == ["--json", "--local"]
    assert f"账户并发上限 · 账户{label}" in invoke(env, "jobs", "local", "--format", "table")[1]
    rc, detail, error = invoke(env, "jobs", "local", "--job-id", "42", "--format", "table")
    assert rc == 0, error
    assert f"SAI 账户限制：{label} · org-parent" in detail
    assert "账户并发上限 (AssocGrpJobsLimit)" in detail
    assert reads == ["cluster-a"] * 3
    assert len(Path(env["TOPOLOGY_CALLS"]).read_text().splitlines()) == 1


@pytest.mark.parametrize("update", [
    {}, {"state_description": "[sai.compute-gate/v1:arrears] account=org-parent"},
    {"state_description": None, "comment": "Arrears: org-parent"},
    {"account_restriction": {"code": "arrears", "account": "forged"}},
])
def test_native_descriptions_and_unknown_fields_never_supply_account_context(native_job, update):
    from sai_cli.local_jobs import _item
    native_job.update(job_state=["PENDING"], state_reason="AssocGrpJobsLimit",
                      state_description="Arrears: org-parent")
    native_job.update(update)
    row = _item(native_job, observed=1790000060).as_dict()
    assert "pending_reason" not in row and "account_restriction" not in row


@pytest.mark.parametrize("change", [
    {"code": "unknown"}, {"account": "bad\x1b[31m"}, {"source": "slurm"}, {"observed_at": True},
])
def test_remote_account_context_is_typed_and_source_bound(job_payload, change):
    row = job_payload["items"][0]
    row.update(state="PD", reason_or_nodelist="AssocGrpJobsLimit",
               account_restriction={"code": "arrears", "account": "org-parent", "secret": "discard",
                                    "source": "sai_applied_policy", "observed_at": 1790000000})
    clean = JobItem.from_payload(row, request_id="r").as_dict()["account_restriction"]
    assert "secret" not in clean
    row["account_restriction"].update(change)
    with pytest.raises(ContractError):
        JobItem.from_payload(row, request_id="r")


@pytest.mark.parametrize("case", ["absent", "invalid", "unsafe", "wrong_cluster", "expired", "other_reason"])
def test_optional_snapshot_failure_keeps_native_rows_and_one_bounded_diagnostic(native_client, account_snapshot, case):
    env, path, payload = native_client
    snapshot_path, snapshot, reads = account_snapshot
    job = payload["jobs"][0]
    job.update(job_state=["PENDING"], state_reason="AssocGrpJobsLimit", state_description="Arrears: private-account")
    if case == "absent":
        snapshot_path.unlink()
    elif case == "invalid":
        snapshot_path.write_text("private-invalid-json")
    elif case == "unsafe":
        snapshot_path.chmod(0o666)
    elif case == "wrong_cluster":
        snapshot["cluster_id"] = "other-cluster"
        snapshot_path.write_text(json.dumps(snapshot))
    elif case == "expired":
        snapshot.update(published_at=int(time.time()) - 301, expires_at=int(time.time()) - 1)
        snapshot_path.write_text(json.dumps(snapshot))
    else:
        job["state_reason"] = "JobHeldUser"
    payload["jobs"].append({**job, "job_id": 43})
    path.write_text(json.dumps(payload))
    rc, output, error = invoke(env, "jobs", "local")
    assert rc == 0
    rows = json.loads(output)["items"]
    assert len(rows) == 2 and all("account_restriction" not in row and "pending_reason" not in row for row in rows)
    assert all(row["reason_or_nodelist"] == job["state_reason"] for row in rows)
    assert len(reads) == (0 if case == "other_reason" else 1)
    assert error.count("account_restrictions_unavailable") == (case in {"invalid", "unsafe", "wrong_cluster"})
    assert str(snapshot_path) not in error and "private" not in error


def test_old_alpha_reason_is_dropped_and_account_context_cannot_attach_to_running_jobs(job_payload):
    row = job_payload["items"][0]
    row["pending_reason"] = {"code": "arrears", "account": "org-parent"}
    assert "pending_reason" not in JobItem.from_payload(row, request_id="r").as_dict()
    row["account_restriction"] = {"code": "arrears", "account": "org-parent", "source": "sai_applied_policy", "observed_at": 1790000000}
    with pytest.raises(ContractError):
        JobItem.from_payload(row, request_id="r")


def test_remote_list_and_allocation_preserve_account_context_without_scope_expansion(tmp_path, site_payload, site_allocation_payload):
    row = site_payload["items"][0]
    row.update(state="PD", state_label="排队中", reason_or_nodelist="AssocGrpJobsLimit",
               account_restriction={"code": "no_compute_funding", "account": "org-parent",
                                    "source": "sai_applied_policy", "observed_at": 1790000000})
    allocation = deepcopy(site_allocation_payload)
    allocation.update(job=deepcopy(row), scheduler_states=["PENDING"], allocation={"status": "not_allocated", "nodes": []})
    with http_endpoint(issuer) as (central, grants), http_endpoint(
        lambda call, _: (200, allocation if "/allocation" in call["path"] else {
            **site_payload, "freshness": {**site_payload["freshness"],
                "source": "scontrol" if call["path"].endswith(row["job_id"]) else "squeue"}})
    ) as (gateway, reads):
        config = profile(tmp_path, central, gateway)
        for words in (["jobs", "list"], ["jobs", "allocation", row["job_id"]]):
            rc, output, error = invoke_remote(config, tmp_path, words)
            assert rc == 0, error
            data = json.loads(output)
            returned = data["job"] if "job" in data else data["items"][0]
            assert returned["account_restriction"] == row["account_restriction"]
            assert returned["reason_or_nodelist"] == "AssocGrpJobsLimit"
        rc, output, error = invoke_remote(config, tmp_path, ["jobs", "show", row["job_id"], "--format", "table"])
        assert rc == 0, error
        assert "SAI 账户限制：资金不足 · org-parent" in output
        assert all(call["bearer"] is None for call in reads)
        assert all("org-parent" not in json.dumps(call["body"]) for call in grants)


def test_tui_account_context_refreshes_from_one_file_and_clears_when_running(topology_client, account_snapshot):
    env, path, payload = topology_client
    snapshot_path, snapshot, _ = account_snapshot
    job = payload["jobs"][0]
    job.update(job_state=["PENDING"], state_reason="AssocGrpJobsLimit",
               state_description="Arrears: org-parent")
    path.write_text(json.dumps(payload))

    async def run():
        queries = Queries(build_parser().parse_args(["tui"]), env)
        async def spawn(arguments):
            entry = "import sys,os;from functools import partial;sys.path.insert(0,sys.argv.pop(1));import sai_cli.local_jobs as jobs;from sai_compute_restrictions import read_snapshot;jobs.read_snapshot=partial(read_snapshot,root=sys.argv.pop(1),trusted_uids=(os.getuid(),));from sai_cli.cli import entrypoint;entrypoint()"
            return await asyncio.create_subprocess_exec(sys.executable, "-I", "-P", "-B", "-c", entry,
                str(Path(__file__).resolve().parents[1] / "src"), str(snapshot_path.parent), *arguments,
                stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE, env=env, start_new_session=True)
        queries._spawn = spawn
        app = QueryApp(queries)
        async with app.run_test(size=(40, 24)) as pilot:
            await loaded(app, pilot)
            screenshot = app.export_screenshot()
            assert "账户欠费" in screenshot and "org-parent" not in screenshot
            await pilot.press("enter")
            await loaded(app, pilot)
            assert app._allocation_detail["job"]["account_restriction"]["account"] == "org-parent"
            snapshot["accounts"]["org-parent"].pop("reason")
            snapshot["accounts"]["org-parent"]["group_jobs_limit"] = None
            snapshot_path.write_text(json.dumps(snapshot))
            await pilot.press("r")
            await loaded(app, pilot)
            assert "account_restriction" not in app._allocation_detail["job"]
            assert "账户欠费" not in app.export_screenshot()
            job.update(job_state=["RUNNING"], state_reason="None")
            path.write_text(json.dumps(payload))
            await pilot.press("r")
            await loaded(app, pilot)
            assert "account_restriction" not in app._allocation_detail["job"]
            assert app._allocation_detail["job"]["reason_or_nodelist"] == job["nodes"]
            assert "欠费" not in app.export_screenshot()
            await pilot.press("q")

    asyncio.run(run())


@pytest.mark.parametrize("native,label,english", [
    ("JobHeldAdmin", "管理员挂起", "Held by administrator"),
    ("DependencyNeverSatisfied", "依赖无法满足", "Unsatisfiable dependency"),
    ("AssocGrpBilling", "账户并发资源上限", "Account resource concurrency limit"),
    ("AssocMaxJobsLimit", "账户内个人并发上限", "Per-user concurrency limit in account"),
    ("QOSGrpBilling", "QOS并发资源上限", "QOS resource concurrency limit"),
    ("QOSGrpGRES", "QOS 通用资源上限", "QOS generic resource limit"),
])
def test_native_reason_presentation_agrees_across_local_http_and_tui(topology_client, tmp_path, site_payload, native, label, english):
    env, path, payload = topology_client
    payload["jobs"][0].update(job_state=["PENDING"], state_reason=native)
    path.write_text(json.dumps(payload))
    rc, output, error = invoke(env, "jobs", "local")
    assert rc == 0, error
    row = json.loads(output)["items"][0]
    assert row["reason_or_nodelist"] == native and "pending_reason" not in row
    assert label in invoke(env, "jobs", "local", "--format", "table")[1]
    rc, detail, error = invoke(env, "jobs", "local", "--job-id", "42", "--format", "table")
    assert rc == 0 and f"{label} ({native})" in detail, error
    assert len(Path(env["TOPOLOGY_CALLS"]).read_text().splitlines()) == 1
    site_payload.update(items=[row], subject={"slurm_user": row["slurm_user"], "slurm_account": None})
    with http_endpoint(issuer) as (central, _), http_endpoint(lambda call, _: (200, {
        **site_payload, "freshness": {**site_payload["freshness"],
            "source": "scontrol" if call["path"].endswith("/42") else "squeue"},
    })) as (gateway, reads):
        config = profile(tmp_path, central, gateway)
        for command in (["jobs", "list"], ["jobs", "list", "--format", "table"], ["jobs", "show", "42", "--format", "table"]):
            rc, output, error = invoke_remote(config, tmp_path, command)
            assert rc == 0, error
            if len(command) == 2:
                assert json.loads(output)["items"][0] == row
            else:
                assert label in output
                assert (native in output) == (command[1] == "show")
        assert len(reads) == 3

    async def run():
        queries = Queries(build_parser().parse_args(["tui"]), env)
        calls, original_spawn = [], queries._spawn
        async def spawn(arguments):
            calls.append(arguments)
            return await original_spawn(arguments)
        queries._spawn = spawn
        app = QueryApp(queries, language="en-US")
        async with app.run_test(size=(100, 24)) as pilot:
            await loaded(app, pilot)
            assert english in unescape(app.export_screenshot()).replace("\xa0", " ")
            assert native not in app.export_screenshot()
            await pilot.press("enter")
            await loaded(app, pilot)
            assert english in unescape(app.export_screenshot()).replace("\xa0", " ")
            assert native in app.export_screenshot()
            assert app._allocation_detail["job"]["reason_or_nodelist"] == native
            assert len(calls) == 2
            await pilot.press("q")
    asyncio.run(run())


def test_running_unknown_and_unmodeled_limit_reasons_keep_the_native_text():
    for native in ("QOSGrpBillingMinutes", "AssocGrpBillingRunMinutes", "QOSGrpGRESFuture", "jobhelduser"):
        row = {"state": "PD", "reason_or_nodelist": native}
        assert job_reason(row) == job_reason(row, detail=True) == native
    assert job_reason({"state": "R", "reason_or_nodelist": "JobHeldAdmin"}, detail=True) == "JobHeldAdmin"
