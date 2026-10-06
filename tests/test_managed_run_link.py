"""The shared correlation field remains usable without a terminal workbench."""
from copy import deepcopy

import pytest

from sai_cli.contracts import JobItem
from sai_cli.errors import ContractError
from sai_cli.managed_runs import ManagedRunDetail
from test_managed_runs_contract import sample


@pytest.mark.parametrize("value", ["", "a" * 63, "A" * 64, "f" * 64 + "\n", 1, False, {}])
def test_run_link_remains_a_typed_allowlisted_value(job_payload, value):
    detail, job = sample("detail"), deepcopy(job_payload["items"][0])
    detail["run"]["run_link"] = job["run_link"] = value
    with pytest.raises(ContractError):
        JobItem.from_payload(job, request_id="invalid")
    with pytest.raises(ContractError):
        ManagedRunDetail.from_payload(detail, workspace_key=detail["workspace_key"], site_id=detail["site_id"],
            run_ref=detail["run"]["run_ref"], request_id="invalid")


def test_shared_read_models_preserve_valid_run_links(job_payload):
    detail, job = sample("detail"), deepcopy(job_payload["items"][0])
    detail["run"]["run_link"] = job["run_link"] = "a" * 64
    native = JobItem.from_payload(job, request_id="native")
    recorded = ManagedRunDetail.from_payload(detail, workspace_key=detail["workspace_key"], site_id=detail["site_id"],
        run_ref=detail["run"]["run_ref"], request_id="recorded")
    assert native.as_dict()["run_link"] == recorded.as_dict()["run"]["run_link"] == "a" * 64
