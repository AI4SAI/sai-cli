from copy import deepcopy
from io import StringIO
import json
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

from sai_cli.auth import TokenLease
from sai_cli.capability import CapabilityLease
from sai_cli.client import JobQuery, PortalClient
from sai_cli.cli import main
from sai_cli.contracts import JobCostResult, JobResult
from sai_cli.errors import ContractError, ForbiddenError
from sai_cli.transport import JsonTransport
from sai_cli.render import render_running_estimate_table
from test_site_transport import http_endpoint, issuer


def test_one_cost_observation_binds_array_task_and_preserves_exact_price(job_cost_payload):
    job = job_cost_payload["items"][0]
    job.update(array_task_id="0", state="S", submit_time="2026-07-31T00:00:00.123456Z")
    job["running_estimate"].update(job_id_raw="12345_0", state="SUSPENDED",
                                   submit_time=job["submit_time"], slurm_job_db_index=2**60)
    result = JobCostResult.from_payload(job_cost_payload, request_id="test")
    assert result.observation.items[0].canonical_id == "12345_0"
    assert result.observation.items[0].values["state"] == "S"
    assert result.estimate.values["gross_cny"] == "2.00000000"
    assert result.estimate.values["slurm_job_db_index"] == 2**60
    assert result.as_dict()["items"][0]["running_estimate"]["slurm_job_db_index"] == 2**60
    assert "running_estimate" not in JobResult.from_payload(job_cost_payload, request_id="test").as_dict()["items"][0]


@pytest.mark.parametrize("key,value", [
    ("job_id_raw", "12345_1"), ("slurm_user", "bob"), ("slurm_account", "org-other"),
    ("submit_time", "2026-07-31T00:00:00.000001Z"), ("start_time", None),
    ("gross_cny", "\x1b[31m2.00000000"), ("final", True), ("state", "PENDING"),
])
def test_cost_rejects_mismatched_identity_and_invalid_price(job_cost_payload, key, value):
    job_cost_payload["items"][0]["running_estimate"][key] = value
    with pytest.raises(ContractError):
        JobCostResult.from_payload(job_cost_payload, request_id="test")


def test_missing_estimate_and_multiple_jobs_are_not_cost_success(job_cost_payload):
    original = deepcopy(job_cost_payload)
    del job_cost_payload["items"][0]["running_estimate"]
    with pytest.raises(ContractError):
        JobCostResult.from_payload(job_cost_payload, request_id="test")
    original["items"].append(deepcopy(original["items"][0]))
    original["count"] = 2
    with pytest.raises(ContractError):
        JobCostResult.from_payload(original, request_id="test")


def test_cost_requires_complete_native_detail_and_accurate_freshness(job_cost_payload):
    for change in ({"has_more": True}, {"freshness": {**job_cost_payload["freshness"], "source": "squeue"}},
                   {"freshness": {**job_cost_payload["freshness"], "age_seconds": 5}}):
        with pytest.raises(ContractError):
            JobCostResult.from_payload({**job_cost_payload, **change}, request_id="test")


def test_cost_keeps_cash_restriction_and_drops_sensitive_additions(job_cost_payload):
    row = job_cost_payload["items"][0]
    row.update(script="private script", environment={"KEY": "private"})
    row["running_estimate"].update(estimate_status="partial", cash_before_credit_cny=None,
                                  uncertainty=["cash_price_restricted"], wallet={"secret": "private"})
    result = JobCostResult.from_payload(job_cost_payload, request_id="test")
    assert result.estimate.values["gross_cny"] == "2.00000000"
    assert result.estimate.values["cash_before_credit_cny"] is None
    assert "private" not in repr(result)
    assert "private" not in json.dumps(result.as_dict())
    rendered = render_running_estimate_table(result, width=40)
    assert "Restricted" in rendered and "2.00" in rendered


def test_cost_uses_central_exact_detail_with_independent_scope_denial(job_cost_payload, monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    requests = []

    def capability(*, request_body, user_lease, **kwargs):
        requests.append(request_body)
        return CapabilityLease(token="opaque-test-capability", expires_at=4_000_000_000,
                               source="fresh", cache_key="test")

    denied = False

    def reply(call, _):
        assert call["bearer"] == "Bearer identity-session-token"
        assert call["capability"] == "opaque-test-capability"
        if denied:
            return 403, {"detail": {"code": "job_cost_read_denied", "message": "No billing scope"}}
        return 200, job_cost_payload

    with http_endpoint(reply) as (portal, calls), http_endpoint(lambda *_: (500, {})) as (gateway, native_calls):
        client = PortalClient(
            transport=JsonTransport(base_url=portal, timeout_seconds=2),
            site_transport=JsonTransport(base_url=gateway, timeout_seconds=2),
            token_provider=SimpleNamespace(get=lambda: TokenLease("identity-session-token", None, "environment")),
            capability_provider=SimpleNamespace(get=capability),
        )
        query = JobQuery(site_id="site-a", cluster_id="cluster-a")
        assert client.job_cost("12345", query).observation.items[0].canonical_id == "12345"
        denied = True
        with pytest.raises(ForbiddenError) as failure:
            client.job_cost("12345", query)
        assert failure.value.code == "job_cost_read_denied"
        denied = False
        with pytest.raises(ContractError):
            client.job_cost("12346", query)
        with pytest.raises(ContractError):
            client.job_cost("12345", JobQuery(site_id="wrong-site", cluster_id="cluster-a"))
        with pytest.raises(ContractError):
            client.job_cost("12345", JobQuery(site_id="site-a", cluster_id="cluster-a", states=("PD",)))
        job_cost_payload.update(scope="org_account", slurm_user=None, slurm_account="personal-alice")
        with pytest.raises(ContractError):
            client.job_cost("12345", JobQuery(site_id="site-a", cluster_id="cluster-a", scope="org-account",
                                               account_name="org-other"))
    parsed = urlsplit(calls[0]["path"])
    assert parsed.path == "/v1/slurm/cli/jobs/12345"
    assert parse_qs(parsed.query)["include_estimate"] == ["true"]
    assert requests[0]["operation"] == "jobs.detail" and requests[0]["job_id"] == "12345"
    assert requests[0]["limit"] is None and requests[0]["partition"] is None
    assert "include_estimate" not in requests[0]
    assert not native_calls


def test_exact_cost_rejects_a_list_only_partition_before_any_request(tmp_path):
    with http_endpoint(lambda *_: pytest.fail("invalid filter must not read")) as (origin, calls):
        out, err = StringIO(), StringIO()
        rc = main(["jobs", "cost", "12345", "--partition", "gpu-standard", "--site", "site-a", "--base-url", origin],
                  environ={"XDG_CONFIG_HOME": str(tmp_path)}, stdout=out, stderr=err)
    assert rc == 2 and not out.getvalue() and not calls
    assert "single-job" in err.getvalue()


@pytest.mark.parametrize("prefix", [True, False])
@pytest.mark.parametrize("output_format", ["json", "table"])
def test_cost_command_reads_exact_array_job_and_preserves_billing_denial(tmp_path, monkeypatch, job_cost_payload, prefix, output_format):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    job_cost_payload["items"][0]["array_task_id"] = "0"
    job_cost_payload["items"][0]["running_estimate"]["job_id_raw"] = "12345_0"
    denied = False
    def reply(call, count):
        if call["method"] == "POST":
            assert call["body"]["operation"] == "jobs.detail" and call["body"]["job_id"] == "12345_0"
            return issuer(call, count)
        parsed = urlsplit(call["path"])
        assert parsed.path == "/v1/slurm/cli/jobs/12345_0"
        assert parse_qs(parsed.query)["include_estimate"] == ["true"]
        if denied:
            return 403, {"detail": {"code": "job_cost_read_denied", "message": "No billing scope"}}
        return 200, job_cost_payload
    with http_endpoint(reply) as (origin, calls), http_endpoint(lambda *_: pytest.fail("cost must stay central")) as (site, native_calls):
        config = tmp_path / "profile.toml"
        config.write_text(f'[profiles.default]\nbase_url="{origin}"\nsite_id="site-a"\ncluster_id="cluster-a"\nsite_read_base_url="{site}"\nrequire_site_capability=true\ncache_path="{tmp_path / "cache" / "tokens.json"}"\n')
        config.chmod(0o600)
        command = ["jobs", "cost", "12345_0", "--format", output_format]
        connection = ["--config", str(config)]
        args = connection + command if prefix else command + connection
        out, err = StringIO(), StringIO()
        env = {"SAI_TOKEN": "identity-session-token"}
        assert main(args, environ=env, stdout=out, stderr=err) == 0 and not err.getvalue(), err.getvalue()
        if output_format == "json":
            estimate = json.loads(out.getvalue())["items"][0]["running_estimate"]
            assert estimate["gross_cny"] == "2.00000000" and estimate["final"] is False
        else:
            assert "12345_0" in out.getvalue() and "2.00" in out.getvalue()
            assert "not settled" in out.getvalue() and "+00:00" in out.getvalue()
            assert "Slurm Account: personal-alice" in out.getvalue()
        assert len(calls) == 2
        denied = True
        out, err = StringIO(), StringIO()
        assert main(args, environ=env, stdout=out, stderr=err) == 4 and not out.getvalue()
        assert "job_cost_read_denied" in err.getvalue() and len(calls) == 3 and not native_calls
