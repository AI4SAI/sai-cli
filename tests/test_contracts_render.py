from __future__ import annotations

from copy import deepcopy
import json

import pytest

from sai_cli.contracts import JOB_ITEM_FIELDS, JobResult
from sai_cli.errors import ContractError
from sai_cli.render import render_json, render_table


def test_contract_allowlists_fields_and_drops_unknown_sensitive_data(job_payload) -> None:
    payload = deepcopy(job_payload)
    payload["raw_provider"] = {"token": "top-level-secret"}
    payload["items"][0].update(
        {
            "work_dir": "/private/path",
            "environment": {"TOKEN": "item-secret"},
            "submit_script": "do-not-emit",
            "raw_json": {"secret": True},
            "wallet_id": "wallet-private",
        }
    )

    result = JobResult.from_payload(payload, request_id="request-1")
    rendered = result.as_dict()

    assert set(rendered["items"][0]) == set(JOB_ITEM_FIELDS)
    text = render_json(rendered)
    assert "top-level-secret" not in text
    assert "item-secret" not in text
    assert "submit_script" not in text
    assert "wallet-private" not in text


@pytest.mark.parametrize(
    "mutation",
    [
        lambda payload: payload.pop("site_id"),
        lambda payload: payload.update(count=2),
        lambda payload: payload.update(items={}),
        lambda payload: payload["items"][0].pop("state"),
        lambda payload: payload["items"][0].update(priority="high"),
        lambda payload: payload["items"][0].update(nodes=-1),
        lambda payload: payload["items"][0].update(name="unsafe\x1b[31m"),
        lambda payload: payload.update(freshness={"source": "squeue"}),
    ],
)
def test_contract_rejects_missing_or_wrong_types(job_payload, mutation) -> None:
    payload = deepcopy(job_payload)
    mutation(payload)
    with pytest.raises(ContractError):
        JobResult.from_payload(payload, request_id="request-invalid")


def test_table_is_deterministic_and_includes_semantic_notes(job_payload) -> None:
    result = JobResult.from_payload(job_payload, request_id="request-table")

    table = render_table(result)

    assert "Job-ID" in table
    assert "simulation" in table
    assert "00:00:00" not in table
    assert "01:00:00" in table
    assert "GPU is the GPU count per node." in table
    assert "MemPerU is host memory per GPU or CPU logical unit." in table
    assert "ANSI" not in table


def test_json_is_valid_and_terminated(job_payload) -> None:
    result = JobResult.from_payload(job_payload, request_id="request-json")
    rendered = render_json(result.as_dict())
    assert rendered.endswith("\n")
    assert json.loads(rendered)["count"] == 1
