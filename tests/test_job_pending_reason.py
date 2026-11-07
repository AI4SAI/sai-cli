"""Native waiting reasons retain separate optional SAI account context."""
import asyncio
from copy import deepcopy
from html import unescape
import json
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
from sai_compute_restrictions import encode_association_comment
from test_local_jobs import native_client, native_job, invoke, number
from test_native_topology import topology_client
from test_site_transport import http_endpoint, issuer, profile, invoke as invoke_remote, site_payload
from test_tui import loaded


def association_comment(reason, revision=1):
    return encode_association_comment("private operator note", account="org-parent", association_id=3,
        owner_ref="11111111-2222-4333-8444-555555555555", revision=revision, reason=reason)


@pytest.fixture
def native_associations(native_client):
    env, source, payload = native_client
    job = payload["jobs"][0]
    job["association_id"] = 47
    source.write_text(json.dumps(payload))
    path = source.parent / "associations.json"
    calls = source.parent / "association-calls.jsonl"
    value = {"associations": [{"id": 47, "cluster": "cluster-a", "account": job["account"],
        "user": job["user_name"], "partition": "", "lineage": f"/org-parent/research/0-{job['user_name']}/",
        "comment": association_comment("arrears")}], "errors": []}
    path.write_text(json.dumps(value))
    binary = source.parent / "sacctmgr"
    binary.write_text(f"#!{sys.executable}\n" + f'''
import json, os, sys
from pathlib import Path
with Path({str(calls)!r}).open('a') as out:
    out.write(json.dumps(sys.argv[1:])+'\\n')
if os.environ.get('ASSOCIATION_FAILURE'):
    print('private-provider-error', file=sys.stderr)
    raise SystemExit(1)
payload = json.loads(Path({str(path)!r}).read_text())
ids = set(map(int, next(arg[4:] for arg in sys.argv[1:] if arg.startswith('Ids=')).split(',')))
payload['associations'] = [row for row in payload['associations'] if row['id'] in ids]
print(json.dumps(payload))
''')
    binary.chmod(0o755)
    return path, value, calls


@pytest.mark.parametrize("code,label", [
    ("arrears", "欠费"), ("severe_arrears", "严重欠费"),
    ("no_compute_funding", "资金不足"), ("admin_blocked", "管理停用"),
])
def test_native_queue_and_exact_detail_keep_separate_account_context(topology_client, native_associations, code, label):
    env, path, payload = topology_client
    association_path, associations, reads = native_associations
    associations["associations"][0]["comment"] = association_comment(code)
    association_path.write_text(json.dumps(associations))
    job = payload["jobs"][0]
    job.update(job_state=["PENDING"], state_reason="AssocGrpJobsLimit",
               state_description="Arrears: ignored-account")
    path.write_text(json.dumps(payload))
    started = int(time.time())
    rc, output, error = invoke(env, "jobs", "local")
    assert rc == 0, error
    row = json.loads(output)["items"][0]
    assert row["reason_or_nodelist"] == "AssocGrpJobsLimit"
    observed = row["account_restriction"]["observed_at"]
    assert started <= observed <= int(time.time())
    assert row["account_restriction"] == {"code": code, "account": "org-parent",
        "source": "sai_applied_policy", "observed_at": observed}
    assert all(value not in output for value in ("private operator note", "association_id", "owner_ref"))
    assert "pending_reason" not in row
    assert row["slurm_account"] == "research"
    assert json.loads(Path(env["NATIVE_CALL"]).read_text())["argv"][0:2] == ["--json", "--local"]
    assert f"账户并发上限 · 账户{label}" in invoke(env, "jobs", "local", "--format", "table")[1]
    rc, detail, error = invoke(env, "jobs", "local", "--job-id", "42", "--format", "table")
    assert rc == 0, error
    assert f"SAI 账户限制：{label} · org-parent" in detail
    assert "账户并发上限 (AssocGrpJobsLimit)" in detail
    assert [json.loads(line) for line in reads.read_text().splitlines()] == [
        ["--json", "show", "association", "where", "Cluster=cluster-a", "Ids=47", "WOPLimits"]] * 3
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


@pytest.mark.parametrize("case", ["absent", "invalid", "unmarked", "wrong_cluster", "native_failure", "other_reason"])
def test_optional_association_failure_keeps_native_rows_and_one_bounded_diagnostic(native_client, native_associations, case):
    env, path, payload = native_client
    association_path, associations, reads = native_associations
    job = payload["jobs"][0]
    job.update(job_state=["PENDING"], state_reason="AssocGrpJobsLimit", state_description="Arrears: private-account")
    if case == "absent":
        associations["associations"] = []
    elif case == "invalid":
        association_path.write_text("private-invalid-json")
    elif case == "unmarked":
        associations["associations"][0]["comment"] = "private operator note"
    elif case == "wrong_cluster":
        associations["associations"][0]["cluster"] = "other-cluster"
    elif case == "native_failure":
        env["ASSOCIATION_FAILURE"] = "1"
    else:
        job["state_reason"] = "JobHeldUser"
    if case != "invalid":
        association_path.write_text(json.dumps(associations))
    payload["jobs"].append({**job, "job_id": 43})
    path.write_text(json.dumps(payload))
    rc, output, error = invoke(env, "jobs", "local")
    assert rc == 0
    rows = json.loads(output)["items"]
    assert len(rows) == 2 and all("account_restriction" not in row and "pending_reason" not in row for row in rows)
    assert all(row["reason_or_nodelist"] == job["state_reason"] for row in rows)
    calls = [json.loads(line) for line in reads.read_text().splitlines()] if reads.exists() else []
    assert calls == ([] if case == "other_reason" else [
        ["--json", "show", "association", "where", "Cluster=cluster-a", "Ids=47", "WOPLimits"]])
    assert error.count("account_restrictions_unavailable") == (case in {"invalid", "native_failure", "wrong_cluster"})
    assert str(association_path) not in error and "private" not in error


def test_old_alpha_reason_is_dropped_and_account_context_cannot_attach_to_running_jobs(job_payload):
    row = job_payload["items"][0]
    row["pending_reason"] = {"code": "arrears", "account": "org-parent"}
    assert "pending_reason" not in JobItem.from_payload(row, request_id="r").as_dict()
    row["account_restriction"] = {"code": "arrears", "account": "org-parent", "source": "sai_applied_policy", "observed_at": 1790000000}
    with pytest.raises(ContractError):
        JobItem.from_payload(row, request_id="r")


@pytest.mark.parametrize("context_kind", ["funding", "limits"])
def test_remote_jobs_preserve_context_without_scope_expansion(tmp_path, site_payload, site_allocation_payload, context_kind):
    row = site_payload["items"][0]
    if context_kind == "funding":
        reason, context_key = "AssocGrpJobsLimit", "account_restriction"
        context = {"code": "no_compute_funding", "account": "org-parent",
                   "source": "sai_applied_policy", "observed_at": 1790000000}
        detail_text = "SAI 账户限制：资金不足 · org-parent"
    else:
        reason, context_key = "AssocGrpBilling", "limit_context"
        context = limit_context(sources=[{"kind": "service_level", "service_level_code": "plus"}])
        detail_text = "并发额度 9007199254740993 billing · 服务等级 Plus"
    row.update(state="PD", state_label="排队中", reason_or_nodelist=reason, **{context_key: context})
    allocation = deepcopy(site_allocation_payload)
    allocation.update(job=deepcopy(row), scheduler_states=["PENDING"], allocation={"status": "not_allocated", "nodes": []})
    with http_endpoint(issuer) as (central, grants), http_endpoint(
        lambda call, _: (200, allocation if "/allocation" in call["path"] else {
            **site_payload, "freshness": {**site_payload["freshness"],
                "source": "scontrol" if call["path"].endswith(row["job_id"]) else "squeue"}})
    ) as (gateway, reads):
        config = profile(tmp_path, central, gateway)
        for words in (["jobs", "list"], ["jobs", "show", row["job_id"]], ["jobs", "allocation", row["job_id"]]):
            rc, output, error = invoke_remote(config, tmp_path, words)
            assert rc == 0, error
            data = json.loads(output)
            returned = data["job"] if "job" in data else data["items"][0]
            assert returned[context_key] == context
            assert returned["reason_or_nodelist"] == reason
        rc, output, error = invoke_remote(config, tmp_path, ["jobs", "show", row["job_id"], "--format", "table"])
        assert rc == 0, error
        assert detail_text in output
        assert all(call["bearer"] is None for call in reads)
        assert all("org-parent" not in json.dumps(call["body"]) for call in grants)


def test_tui_account_context_refreshes_from_native_association_and_clears_when_running(topology_client, native_associations):
    env, path, payload = topology_client
    association_path, associations, reads = native_associations
    job = payload["jobs"][0]
    job.update(job_state=["PENDING"], state_reason="AssocGrpJobsLimit",
               state_description="Arrears: org-parent")
    path.write_text(json.dumps(payload))

    async def run():
        queries = Queries(build_parser().parse_args(["tui"]), env)
        app = QueryApp(queries)
        async with app.run_test(size=(40, 24)) as pilot:
            await loaded(app, pilot)
            screenshot = app.export_screenshot()
            assert "账户欠费" in screenshot and "org-parent" not in screenshot
            await pilot.press("enter")
            await loaded(app, pilot)
            assert app._allocation_detail["job"]["account_restriction"]["account"] == "org-parent"
            associations["associations"][0]["comment"] = association_comment(None, revision=2)
            association_path.write_text(json.dumps(associations))
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
            assert len(reads.read_text().splitlines()) == 3
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


@pytest.fixture
def native_limits(native_associations):
    path, payload, calls = native_associations
    user = payload["associations"][0]
    owner = "11111111-2222-4333-8444-555555555555"

    def values(billing=None, submit=None):
        return {"jobs": {"per": {"count": number(0, present=False)},
                         "total": number(submit or 0, present=submit is not None)},
                "tres": {"total": [] if billing is None else [
                    {"type": "billing", "id": 5, "name": "", "count": billing}]}}

    def limits(billing, submit, sources):
        return {"billing_tres_limit": {"value": billing, "sources": sources},
                "max_submit_jobs": {"value": submit, "sources": sources}}

    parent_sources = [{"kind": "service_level", "service_level_code": "pro"}, {"kind": "reservation"}]
    account_sources = [{"kind": "org_admin"}, {"kind": "hard_clamp"}]
    member_sources = [{"kind": "member_limit"}]
    root = {"id": 1, "cluster": "cluster-a", "account": "root", "user": "", "partition": "",
            "lineage": "/", "comment": "private root note", "max": values()}
    parents = []
    for ident, account, lineage, billing, submit, sources in (
        (3, "org-parent", "/org-parent/", 512, 80, parent_sources),
        (4, "research", "/org-parent/research/", 128, 40, account_sources),
    ):
        parents.append({"id": ident, "cluster": "cluster-a", "account": account, "user": "",
            "partition": "", "lineage": lineage, "max": values(billing, submit),
            "comment": encode_association_comment("private operator note", account=account,
                association_id=ident, owner_ref=owner, revision=1, reason=None,
                limits=limits(billing, submit, sources))})
    user.update(max=values(64, 20), comment=encode_association_comment(
        "private member note", account="research", association_id=4, owner_ref=owner,
        revision=1, reason=None, ancestor_ids=[1, 3, 4],
        member={"association_id": user["id"], "owner_ref": owner, "revision": 1,
                "limits": limits(64, 20, member_sources)}))
    payload["associations"] = [user, root, *parents]
    path.write_text(json.dumps(payload))
    return path, payload, calls


@pytest.mark.parametrize("native,field,amounts,title", [
    ("AssocGrpBilling", "billing_tres_limit", ["512", "128", "64"], "并发额度"),
    ("AssocMaxSubmitJobLimit", "max_submit_jobs", ["80", "40", "20"], "提交作业数上限"),
])
def test_native_limit_layers_share_queue_detail_reader_and_keep_lists_short(
    topology_client, native_limits, native, field, amounts, title,
):
    env, path, payload = topology_client
    payload["jobs"][0].update(job_state=["PENDING"], state_reason=native)
    payload["jobs"].append({**payload["jobs"][0], "job_id": 43})
    path.write_text(json.dumps(payload))
    association_path, associations, calls = native_limits
    rc, output, error = invoke(env, "jobs", "local")
    assert rc == 0 and not error
    rows = json.loads(output)["items"]
    assert rows[0]["limit_context"] == rows[1]["limit_context"]
    context = rows[0]["limit_context"]
    expected = [
        ("org-parent", "account", field, amounts[0]), ("research", "account", field, amounts[1]),
        ("research", "member", field, amounts[2]),
    ]
    if field == "max_submit_jobs":
        expected = expected[-1:]
    assert [(item["account"], item["scope"], item["field"], item["value"]) for item in context["constraints"]] == expected
    assert all(word not in output for word in ("private", "owner_ref", "association_id", "revision", "comment"))
    rc, table, error = invoke(env, "jobs", "local", "--format", "table")
    assert rc == 0 and "来源" not in table and "服务等级" not in table
    assert "org-parent" not in table
    rc, detail, error = invoke(env, "jobs", "local", "--job-id", "42", "--format", "table")
    assert rc == 0 and not error
    assert all(f"{title} {item[-1]}" in detail for item in expected)
    assert "成员设置" in detail
    if field == "billing_tres_limit":
        assert "服务等级 Pro + 预留容量" in detail and "组织设置" in detail
    else:
        assert "org-parent" not in detail and "组织设置" not in detail
    assert native in detail
    assert [json.loads(line) for line in calls.read_text().splitlines()] == [
        ["--json", "show", "association", "where", "Cluster=cluster-a", "Ids=47", "WOPLimits"],
        ["--json", "show", "association", "where", "Cluster=cluster-a", "Ids=1,3,4", "WOPLimits"],
    ] * 3
    assert len(Path(env["TOPOLOGY_CALLS"]).read_text().splitlines()) == 1


def limit_context(value="9007199254740993", sources=None):
    return {"observed_at": 1790000000, "constraints": [{"account": "org-parent", "scope": "account",
        "field": "billing_tres_limit", "value": value, "sources": [] if sources is None else sources}]}


def test_limit_dto_keeps_uint64_precision_and_drops_private_envelope_fields(job_payload):
    row = job_payload["items"][0]
    row.update(state="PD", reason_or_nodelist="AssocGrpBilling", limit_context=limit_context())
    row["limit_context"]["private_note"] = "do not expose"
    row["limit_context"]["constraints"][0]["owner_ref"] = "do not expose"
    clean = JobItem.from_payload(row, request_id="limits").as_dict()
    assert clean["limit_context"] == limit_context()
    assert "9007199254740993" in job_reason(clean, detail=True)
    assert "来源未核实" in job_reason(clean, detail=True)
    assert "服务等级" not in job_reason(clean, detail=True)
    assert job_reason(clean) == "账户并发资源上限"


@pytest.mark.parametrize("change", [
    {"value": 128}, {"value": 128.0}, {"value": True}, {"value": "01"}, {"value": "-1"},
    {"value": "18446744073709551614"}, {"account": "org\x1b[31m"}, {"scope": "parent"},
    {"field": "max_submit_jobs"}, {"sources": [{"kind": "unknown"}]},
    {"sources": [{"kind": "service_level", "service_level_code": "unknown"}]},
    {"sources": [{"kind": "org_admin", "actor": "private"}]},
    {"sources": [{"kind": "grant", "grant_kind": "unknown"}]},
    {"sources": [{"kind": "hard_clamp"}, {"kind": "hard_clamp"}]},
])
def test_invalid_remote_limit_context_is_rejected(job_payload, change):
    row = job_payload["items"][0]
    context = limit_context()
    context["constraints"][0].update(change)
    row.update(state="PD", reason_or_nodelist="AssocGrpBilling", limit_context=context)
    with pytest.raises(ContractError):
        JobItem.from_payload(row, request_id="limits")


@pytest.mark.parametrize("state,reason", [
    ("R", "AssocGrpBilling"), ("PD", "QOSGrpBilling"), ("PD", "AssociationJobLimit"),
    ("PD", "AssocGrpSubmitJobsLimit"), ("PD", "AssocGrpJobsLimit"),
])
def test_limit_context_cannot_attribute_unrelated_native_reasons(job_payload, state, reason):
    row = job_payload["items"][0]
    row.update(state=state, reason_or_nodelist=reason, limit_context=limit_context())
    with pytest.raises(ContractError):
        JobItem.from_payload(row, request_id="limits")


def test_submit_limit_dto_rejects_multiple_inherited_layers(job_payload):
    row = job_payload["items"][0]
    context = limit_context("20")
    context["constraints"][0]["field"] = "max_submit_jobs"
    row.update(state="PD", reason_or_nodelist="AssocMaxSubmitJobLimit", limit_context=context)
    assert JobItem.from_payload(row, request_id="limits").as_dict()["limit_context"] == context
    context["constraints"].append({**context["constraints"][0], "scope": "member"})
    with pytest.raises(ContractError):
        JobItem.from_payload(row, request_id="limits")


def test_limit_sources_show_contributions_and_independent_clamps_without_actor_claims():
    row = {"state": "PD", "reason_or_nodelist": "AssocGrpBilling", "limit_context": limit_context(
        sources=[{"kind": "service_level", "service_level_code": "personal_standard"},
                 {"kind": "reservation"}, {"kind": "project_pi"}, {"kind": "hard_clamp"}])}
    assert job_reason(row, detail=True) == (
        "账户并发资源上限 (AssocGrpBilling)\n"
        "org-parent 账户 · 并发额度 9007199254740993 billing · 服务等级 标准 + 预留容量、项目设置、手动上限"
    )
    english = job_reason(row, detail=True, language="en-US")
    assert "Service level Standard + Reserved capacity, Project setting, Manual cap" in english
    assert "9007199254740993 billing" in english
    row["limit_context"]["constraints"][0]["sources"].insert(
        1, {"kind": "grant", "grant_kind": "subscription"})
    assert "(服务等级 标准、订阅授予) + 预留容量" in job_reason(row, detail=True)


@pytest.mark.parametrize("kind,label", [
    ("baseline", "基准授予"), ("assurance", "保障授予"), ("contract", "合同授予"),
    ("subscription", "订阅授予"), ("trial", "试用授予"), ("mis", "管理授予"),
])
def test_grant_source_uses_its_verified_category(kind, label):
    row = {"state": "PD", "reason_or_nodelist": "AssocGrpBilling", "limit_context": limit_context(
        sources=[{"kind": "grant", "grant_kind": kind}])}
    detail = job_reason(row, detail=True)
    assert label in detail and "服务等级" not in detail


def test_tui_limit_refresh_retains_native_number_when_sources_change(topology_client, native_limits):
    env, path, payload = topology_client
    job = payload["jobs"][0]
    job.update(job_state=["PENDING"], state_reason="AssocGrpBilling")
    path.write_text(json.dumps(payload))
    association_path, associations, calls = native_limits

    async def run():
        app = QueryApp(Queries(build_parser().parse_args(["tui"]), env))
        async with app.run_test(size=(40, 24)) as pilot:
            await loaded(app, pilot)
            assert "服务等级" not in app.export_screenshot()
            await pilot.press("enter")
            await loaded(app, pilot)
            assert len(app._allocation_detail["job"]["limit_context"]["constraints"]) == 3
            assert "服务等级" in unescape(app.export_screenshot())
            associations["associations"][2]["max"]["tres"]["total"][0]["count"] = 600
            association_path.write_text(json.dumps(associations))
            await pilot.press("r")
            await loaded(app, pilot)
            parent = app._allocation_detail["job"]["limit_context"]["constraints"][0]
            assert parent["value"] == "600" and parent["sources"] == []
            assert "来源未核实" in unescape(app.export_screenshot())
            job.update(job_state=["RUNNING"], state_reason="None")
            path.write_text(json.dumps(payload))
            await pilot.press("r")
            await loaded(app, pilot)
            assert "limit_context" not in app._allocation_detail["job"]
            assert "来源未核实" not in app.export_screenshot()
            assert len(calls.read_text().splitlines()) == 6
            await pilot.press("q")
    asyncio.run(run())
