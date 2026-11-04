"""One native observation supplies pending reasons to every job presentation."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path

import pytest

from sai_cli.cli import build_parser
from sai_cli.contracts import JobItem
from sai_cli.errors import ContractError
from sai_cli.tui import QueryApp
from sai_cli.tui_queries import Queries
from test_local_jobs import native_client, native_job, invoke
from test_native_topology import topology_client
from test_site_transport import http_endpoint, issuer, profile, invoke as invoke_remote, site_payload
from test_tui import loaded


@pytest.mark.parametrize("code,native_label,label", [
    ("arrears", "Arrears", "欠费"), ("severe_arrears", "Severe arrears", "严重欠费"),
    ("no_compute_funding", "No compute funds", "资金不足"), ("admin_blocked", "Admin disabled", "管理停用"),
])
def test_native_queue_and_exact_detail_keep_reason_and_actual_blocker(topology_client, code, native_label, label):
    env, path, payload = topology_client
    job = payload["jobs"][0]
    job.update(job_state=["PENDING"], state_reason="AssocGrpJobsLimit",
               state_description=f"{native_label}: org-parent")
    path.write_text(json.dumps(payload))
    rc, output, error = invoke(env, "jobs", "local")
    assert rc == 0, error
    row = json.loads(output)["items"][0]
    assert row["reason_or_nodelist"] == "AssocGrpJobsLimit"
    assert row["pending_reason"] == {"code": code, "account": "org-parent"}
    assert row["slurm_account"] == "research"
    assert json.loads(Path(env["NATIVE_CALL"]).read_text())["argv"][0:2] == ["--json", "--local"]
    assert label in invoke(env, "jobs", "local", "--format", "table")[1]
    rc, detail, error = invoke(env, "jobs", "local", "--job-id", "42", "--format", "table")
    assert rc == 0, error
    assert label in detail and "阻塞账户 org-parent" in detail
    assert len(Path(env["TOPOLOGY_CALLS"]).read_text().splitlines()) == 1


@pytest.mark.parametrize("update", [
    {"job_state": ["RUNNING"]}, {"state_reason": "Resources"},
    {"state_description": "Unknown: org-parent"},
    {"state_description": "Arrears: org-parent extra"},
    {"state_description": "[sai.compute-gate/v1:arrears] account=org-parent"},
    {"state_description": None, "comment": "Arrears: org-parent"},
])
def test_native_nonmatching_observations_never_acquire_a_business_reason(native_job, update):
    from sai_cli.local_jobs import _item
    native_job.update(job_state=["PENDING"], state_reason="AssocGrpJobsLimit",
                      state_description="Arrears: org-parent")
    native_job.update(update)
    assert "pending_reason" not in _item(native_job, observed=1790000060).as_dict()


@pytest.mark.parametrize("change", [
    {"pending_reason": {"code": "unknown", "account": "org-parent"}},
    {"pending_reason": {"code": "arrears", "account": "bad\x1b[31m"}},
    {"pending_reason": "arrears"}, {"state": "R"}, {"reason_or_nodelist": "Resources"},
])
def test_remote_reason_allowlist_rejects_malformed_or_stale_business_facts(job_payload, change):
    row = job_payload["items"][0]
    row.update(state="PD", reason_or_nodelist="AssocGrpJobsLimit",
               pending_reason={"code": "arrears", "account": "org-parent", "secret": "discard"})
    assert JobItem.from_payload(row, request_id="r").as_dict()["pending_reason"] == {
        "code": "arrears", "account": "org-parent"}
    row.update(change)
    with pytest.raises(ContractError):
        JobItem.from_payload(row, request_id="r")


def test_remote_list_and_allocation_preserve_pending_reason_without_scope_expansion(tmp_path, site_payload, site_allocation_payload):
    row = site_payload["items"][0]
    row.update(state="PD", state_label="排队中", reason_or_nodelist="AssocGrpJobsLimit",
               pending_reason={"code": "no_compute_funding", "account": "org-parent"})
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
            assert returned["pending_reason"] == row["pending_reason"]
            assert returned["reason_or_nodelist"] == "AssocGrpJobsLimit"
        rc, output, error = invoke_remote(config, tmp_path, ["jobs", "show", row["job_id"], "--format", "table"])
        assert rc == 0, error
        assert "资金不足 · 阻塞账户 org-parent" in output
        assert all(call["bearer"] is None for call in reads)
        assert all("org-parent" not in json.dumps(call["body"]) for call in grants)


def test_tui_pending_detail_and_refresh_drop_the_previous_business_reason(topology_client):
    env, path, payload = topology_client
    job = payload["jobs"][0]
    job.update(job_state=["PENDING"], state_reason="AssocGrpJobsLimit",
               state_description="Arrears: org-parent")
    path.write_text(json.dumps(payload))

    async def run():
        app = QueryApp(Queries(build_parser().parse_args(["tui"]), env))
        async with app.run_test(size=(40, 24)) as pilot:
            await loaded(app, pilot)
            screenshot = app.export_screenshot()
            assert "欠费" in screenshot and "org-parent" in screenshot
            await pilot.press("enter")
            await loaded(app, pilot)
            assert app._allocation_detail["job"]["pending_reason"]["account"] == "org-parent"
            job.update(job_state=["RUNNING"], state_reason="None")
            path.write_text(json.dumps(payload))
            await pilot.press("r")
            await loaded(app, pilot)
            assert "pending_reason" not in app._allocation_detail["job"]
            assert "欠费" not in app.export_screenshot()
            await pilot.press("q")

    asyncio.run(run())
