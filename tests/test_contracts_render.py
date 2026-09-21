from __future__ import annotations

from copy import deepcopy
import json

import pytest

from sai_cli.contracts import (
    AccountStatus,
    JOB_ITEM_FIELDS,
    RUNNING_ESTIMATE_ALLOC_TRES_FIELDS,
    RUNNING_ESTIMATE_ITEM_FIELDS,
    RUNNING_ESTIMATE_RESOURCE_FIELDS,
    JobResult,
    RunningEstimateResult,
)
from sai_cli.errors import ContractError
from sai_cli.render import render_account_status, render_json, render_running_estimate_table, render_table


def test_account_status_allowlist_and_table_output() -> None:
    payload = {
        "schema_version": "account.status/v1",
        "verification_current": False,
        "access_state": "normal",
        "initial_verification_deadline": "2027-09-21T00:00:00Z",
        "verification_url": "/portal/#/portal/account/identity-assurance",
        "raw": {"token": "must-not-appear", "evidence": "private"},
    }
    status = AccountStatus.from_payload(payload, request_id="account-status")
    assert "raw" not in status.as_dict()
    assert "365" in render_account_status(status)
    assert "must-not-appear" not in render_json(status.as_dict())
    for key, value in (("verification_url", "https://outside.example/"),
                       ("initial_verification_deadline", "2027-09-21T00:00:00"),
                       ("access_state", "\x1b[31m"), ("verification_current", "true")):
        with pytest.raises(ContractError):
            AccountStatus.from_payload({**payload, key: value}, request_id="account-status")


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


@pytest.mark.parametrize(
    "mutation",
    [
        lambda payload: payload.update(scope="ops_all"),
        lambda payload: payload.update(slurm_user="other-user"),
        lambda payload: payload["items"][0].update(slurm_user="other-user"),
        lambda payload: payload.update(slurm_account="private-alice"),
    ],
)
def test_job_contract_rejects_scope_or_subject_overread(job_payload, mutation) -> None:
    payload = deepcopy(job_payload)
    mutation(payload)
    with pytest.raises(ContractError):
        JobResult.from_payload(payload, request_id="request-overread")


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


def test_running_estimate_contract_recursively_drops_unknown_fields(running_estimate_payload) -> None:
    payload = deepcopy(running_estimate_payload)
    payload["wallet"] = {"token": "top-secret"}
    payload["freshness"]["raw_source"] = "private-source"
    payload["items"][0]["ledger"] = {"secret": "ledger-secret"}
    payload["items"][0]["cash_cny"] = "9.99999999"
    payload["items"][0]["resources"]["raw_tres"] = "raw-secret"
    payload["items"][0]["resources"]["alloc_tres"]["native"] = "native-secret"

    rendered = RunningEstimateResult.from_payload(payload, request_id="estimate-request").as_dict()

    assert set(rendered["items"][0]) == set(RUNNING_ESTIMATE_ITEM_FIELDS)
    assert set(rendered["items"][0]["resources"]) == set(RUNNING_ESTIMATE_RESOURCE_FIELDS)
    assert set(rendered["items"][0]["resources"]["alloc_tres"]) == set(
        RUNNING_ESTIMATE_ALLOC_TRES_FIELDS
    )
    text = render_json(rendered)
    for secret in ("top-secret", "private-source", "ledger-secret", "raw-secret", "native-secret"):
        assert secret not in text
    assert "cash_cny" not in rendered["items"][0]


@pytest.mark.parametrize(
    "mutation",
    [
        lambda payload: payload.update(final=True),
        lambda payload: payload.update(operation="jobs.list"),
        lambda payload: payload.update(schema_version="billing.running-estimate.v1"),
        lambda payload: payload.pop("visibility_role"),
        lambda payload: payload.update(site_timezone="+08:00"),
        lambda payload: payload["freshness"].update(stale="false"),
        lambda payload: payload["freshness"].update(stale=True),
        lambda payload: payload["freshness"].update(observed_at="2026-08-14T09:02:00+08:00"),
        lambda payload: payload["items"][0].update(start_time="2026-08-14T00:02:00"),
        lambda payload: payload["items"][0].update(gross_cny="2.0"),
        lambda payload: payload["items"][0].update(cash_before_credit_cny=None),
        lambda payload: payload["items"][0].update(price_revision="price-v1"),
        lambda payload: payload["items"][0].update(price_revision="A" * 64),
        lambda payload: payload["items"][0].update(uncertainty=["pricing_uncertain"]),
        lambda payload: payload["items"][0].update(
            estimate_status="partial",
            cash_before_credit_cny=None,
            uncertainty=[],
        ),
        lambda payload: payload["items"][0].update(
            estimate_status="partial",
            uncertainty=["payer_unavailable"],
        ),
        lambda payload: payload["items"][0].update(estimate_status="settled"),
        lambda payload: payload["items"][0]["resources"].update(resource_count=True),
        lambda payload: payload["items"][1]["resources"].update(usage_quantity="0"),
        lambda payload: payload["items"][2].update(gross_cny="1.00000000"),
        lambda payload: payload["items"][2].update(uncertainty=[]),
        lambda payload: payload["items"][2].update(uncertainty=[{"message": "raw"}]),
    ],
)
def test_running_estimate_contract_rejects_invalid_semantics(
    running_estimate_payload,
    mutation,
) -> None:
    payload = deepcopy(running_estimate_payload)
    mutation(payload)
    with pytest.raises(ContractError):
        RunningEstimateResult.from_payload(payload, request_id="estimate-invalid")


def test_running_estimate_contract_accepts_partial_before_credit_estimate(
    running_estimate_payload,
) -> None:
    payload = deepcopy(running_estimate_payload)
    payload["items"][0].update(
        estimate_status="partial",
        cash_before_credit_cny=None,
        uncertainty=["payer_unavailable"],
    )

    result = RunningEstimateResult.from_payload(payload, request_id="estimate-partial")

    assert result.as_dict()["items"][0]["estimate_status"] == "partial"


def test_running_estimate_table_shows_freshness_and_estimate_states(running_estimate_payload) -> None:
    result = RunningEstimateResult.from_payload(
        running_estimate_payload,
        request_id="estimate-table",
    )

    table = render_running_estimate_table(result)

    assert "Timezone: Asia/Shanghai" in table
    assert "As-of: 2026-08-14T09:02:03+08:00" in table
    assert "Observed: 2026-08-14T09:02:00+08:00" in table
    assert "Age: 3s" in table
    assert "Stale: no" in table
    assert "ETag: snapshot-etag" in table
    assert "PENDING" in table
    assert "UNAVAILABLE" in table
    assert "Gross est. CNY" in table
    assert "Before-credit CNY" not in table
    assert "Gross amounts are running estimates only" in table
