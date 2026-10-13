"""An HTTP success must still answer the caller's exact query."""
from copy import deepcopy
from io import StringIO
import json

import pytest

from sai_cli.cli import main
from test_site_transport import http_endpoint, issuer


@pytest.mark.parametrize("capability", [False, True])
@pytest.mark.parametrize("operation", ["list", "show", "exact-cost", "estimates"])
def test_central_job_reads_reject_expanded_response_filters(
    tmp_path, job_payload, job_cost_payload, running_estimate_payload, capability, operation,
):
    original = deepcopy(running_estimate_payload if operation == "estimates" else
                        job_cost_payload if operation == "exact-cost" else job_payload)
    original.update(scope="project_account", slurm_user=None, slurm_account="project-selected")
    original["items"] = original["items"][:1]
    original["count"] = 1
    original["items"][0]["slurm_account"] = "project-selected"
    if operation == "exact-cost":
        original["items"][0]["running_estimate"]["slurm_account"] = "project-selected"
    if operation == "show":
        original["freshness"]["source"] = "scontrol"
    command = {
        "list": ["jobs", "list", "--partition", "gpu-standard", "--limit", "1"],
        "show": ["jobs", "show", "12345"],
        "exact-cost": ["jobs", "cost", "12345"],
        "estimates": ["jobs", "cost", "--partition", "gpu-standard"],
    }[operation] + ["--scope", "project-account", "--account", "project-selected", "--states", "RUNNING"]
    response = original

    def reply(call, count):
        if call["method"] == "POST":
            return issuer(call, count)
        assert call["path"].startswith("/v1/" + ("billing/" if operation == "estimates" else "slurm/"))
        return 200, response

    mismatches = [None, "account", "state"]
    if operation in {"list", "estimates"}:
        mismatches.append("partition")
    if operation == "list":
        mismatches.append("limit")
    if operation in {"show", "exact-cost"}:
        mismatches.append("job")
    with http_endpoint(reply) as (origin, calls):
        config = tmp_path / "config.toml"
        config.write_text('[profiles.default]\nsite_id="site-a"\ncluster_id="cluster-a"\n'
                          f'base_url={json.dumps(origin)}\nrequire_site_capability={str(capability).lower()}\n')
        config.chmod(0o600)
        env = {"SAI_TOKEN": "identity-session-token", "XDG_CACHE_HOME": str(tmp_path / "cache")}
        for mismatch in mismatches:
            response = deepcopy(original)
            row = response["items"][0]
            if mismatch == "account":
                response["slurm_account"] = row["slurm_account"] = "project-unrequested"
                if operation == "exact-cost":
                    row["running_estimate"]["slurm_account"] = "project-unrequested"
            elif mismatch == "state":
                row["state"] = "PENDING"
                if operation == "exact-cost":
                    row["running_estimate"]["state"] = "PENDING"
            elif mismatch == "partition":
                (row["resources"] if operation == "estimates" else row)["partition"] = "cpu-other"
            elif mismatch == "limit":
                response["items"].append({**row, "job_id": "12346"})
                response["count"] = 2
            elif mismatch == "job":
                row["job_id"] = "12346"
                if operation == "exact-cost":
                    row["running_estimate"]["job_id_raw"] = "12346"
            output, error = StringIO(), StringIO()
            code = main(["--config", str(config), *command], environ=env, stdout=output, stderr=error)
            if mismatch is None:
                assert code == 0, error.getvalue()
                assert json.loads(output.getvalue())["items"][0]["slurm_account"] == "project-selected"
            else:
                assert code == 7 and output.getvalue() == "", (mismatch, error.getvalue(), output.getvalue())
                assert json.loads(error.getvalue())["error"]["code"] == "contract_invalid"
        assert any(call["method"] == "POST" for call in calls) is capability


def test_organization_binding_keeps_authorized_child_intersection(job_payload):
    from sai_cli.contracts import JobResult
    from sai_cli.errors import ContractError
    payload = deepcopy(job_payload)
    payload.update(schema_version="jobs.portal/v2", scope="org_account", slurm_account="org-selected",
                   slurm_user=None, subaccounts=[{"slurm_account": "project-child", "slurm_user": "alice"}])
    payload["items"][0]["slurm_account"] = "project-child"
    binding = dict(site_id="site-a", cluster_id="cluster-a", scope="org_account", account_name="org-selected",
                   partition="gpu-standard", states=("RUNNING",), limit=1, request_id="org-binding")
    JobResult.from_payload(payload, request_id="org-binding").require_request_binding(**binding)
    with pytest.raises(ContractError):
        JobResult.from_payload(payload, request_id="org-binding").require_request_binding(
            **{**binding, "account_name": "org-other"})
    payload["items"][0]["slurm_user"] = "bob"
    with pytest.raises(ContractError):
        JobResult.from_payload(payload, request_id="org-binding")


def test_running_estimates_remain_complete_without_an_invented_list_limit(tmp_path, running_estimate_payload):
    from types import SimpleNamespace
    from sai_cli.auth import TokenLease
    from sai_cli.client import JobQuery, PortalClient
    from sai_cli.transport import JsonTransport
    with http_endpoint(lambda *_: (200, running_estimate_payload)) as (origin, calls):
        client = PortalClient(transport=JsonTransport(base_url=origin, timeout_seconds=2),
                              token_provider=SimpleNamespace(get=lambda: TokenLease("synthetic", None, "environment")))
        result = client.running_estimates(JobQuery(site_id="site-a", limit=1))
    assert len(result.items) == 3 and "limit=" not in calls[0]["path"]
