from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import time

import pytest

from sai_cli.errors import ContractError
from sai_cli.render import render_site_placement
from sai_cli.site_placement import SiteJobPlacementResult
from test_site_transport import http_endpoint, issuer, profile, invoke


def sample():
    return json.loads((Path(__file__).resolve().parents[1] / "contracts/job-placement/v1/sample.json").read_text())


def current_placement(value=None):
    result = sample() if value is None else deepcopy(value)
    now = datetime.now(timezone.utc)
    utc = lambda delta: (now + timedelta(seconds=delta)).isoformat().replace("+00:00", "Z")
    result["allocation"]["freshness"]["observed_at"] = utc(0)
    if result["inventory"] is not None:
        result["inventory"].update(published_at=utc(-10), expires_at=utc(300))
        for node in result["nodes"]:
            if node["registration"] is not None:
                node["registration"].update(verified_at=utc(-20), valid_until=utc(200))
    return result


def parse(value):
    return SiteJobPlacementResult.from_payload(value, request_id="placement-test")


def test_shared_placement_round_trip_and_recursive_allowlist():
    value = sample()
    expected = deepcopy(value)
    for row in (value, value["inventory"], value["nodes"][0], value["nodes"][0]["registration"],
                value["nodes"][0]["registration"]["rack"], value["allocation"], value["allocation"]["job"]):
        row["secret"] = "/private/not-for-output"
    result = parse(value)
    assert result.as_dict() == expected
    assert "private" not in render_site_placement(result)
    assert "Rack A, U12, height 4U" in render_site_placement(result)
    assert "Verified:" in render_site_placement(result)


@pytest.mark.parametrize("mutate", [
    lambda p: p.update(schema_version="jobs.allocation/v2"),
    lambda p: p.update(coverage="all_nodes"), lambda p: p.update(inventory=None),
    lambda p: p["inventory"].update(generation=True), lambda p: p["inventory"].update(generation=1.0),
    lambda p: p["inventory"].update(generation=0), lambda p: p["inventory"].update(generation=2**53),
    lambda p: p["inventory"].update(revision="bad"),
    lambda p: p["inventory"].update(published_at="2026-09-23T00:00:02Z"),
    lambda p: p["inventory"].update(expires_at="2026-09-23T00:00:01Z"),
    lambda p: p["inventory"].update(published_at="2026-02-30T00:00:00Z"),
    lambda p: p["nodes"].reverse(), lambda p: p["nodes"].pop(),
    lambda p: p["nodes"][0].update(status="current_verified"),
    lambda p: p["nodes"][0].update(status="expired"),
    lambda p: p["nodes"][0].update(registration=None),
    lambda p: p["nodes"][0].update(name="other-node"),
    lambda p: p["nodes"][0]["registration"].update(asset_ref="asset/private"),
    lambda p: p["nodes"][0]["registration"].update(incarnation_ref="asset\n"),
    lambda p: p["nodes"][0]["registration"].update(label="\x1bunsafe"),
    lambda p: p["nodes"][0]["registration"].update(label="x" * 129),
    lambda p: p["nodes"][0]["registration"].update(verified_at="2026-09-22T23:00:00.1Z"),
    lambda p: p["nodes"][0]["registration"].update(valid_until="2026-09-23T00:00:01Z"),
    lambda p: p["nodes"][0]["registration"].update(valid_until="2026-09-25T00:00:00Z"),
    lambda p: p["nodes"][0]["registration"].update(placement_ref=None),
    lambda p: p["nodes"][0]["registration"].update(rack=None),
    lambda p: p["nodes"][0]["registration"]["rack"].update(u_start=0),
    lambda p: p["nodes"][0]["registration"]["rack"].update(u_height=True),
    lambda p: p["nodes"][0]["registration"]["rack"].update(u_height=4.0),
    lambda p: p["nodes"][0]["registration"]["rack"].update(u_start=99),
    lambda p: p["nodes"][0]["registration"]["rack"].update(ref="rack\x85"),
])
def test_placement_rejects_invalid_registration(mutate):
    value = sample()
    mutate(value)
    with pytest.raises(ContractError):
        parse(value)


def test_every_placement_field_is_required():
    for path in ((), ("inventory",), ("nodes", 0), ("nodes", 0, "registration"), ("nodes", 0, "registration", "rack")):
        row = sample()
        for part in path:
            row = row[part]
        for field in row:
            value = sample()
            target = value
            for part in path:
                target = target[part]
            del target[field]
            with pytest.raises(ContractError):
                parse(value)


def test_unknown_and_expired_records_never_turn_into_zero_location():
    value = sample()
    value["nodes"][0]["registration"].update(rack=None, placement_ref=None)
    value["nodes"][1]["status"] = "expired"
    assert parse(value).as_dict() == value
    assert "Location unknown" in render_site_placement(parse(value))
    assert "Record expired" in render_site_placement(parse(value))
    for status, nodes in (("not_allocated", []), ("unavailable", None)):
        value["allocation"]["allocation"] = {"status": status, "nodes": nodes}
        value.update(inventory=None, nodes=[])
        assert parse(value).as_dict() == value


def test_registration_references_rack_labels_and_returned_u_ranges_are_consistent():
    value = sample()
    value["nodes"][1].update(status="recorded", registration=deepcopy(value["nodes"][0]["registration"]))
    second = value["nodes"][1]["registration"]
    second.update(asset_ref="asset-b", incarnation_ref="instance-b", placement_ref="placement-b")
    second["rack"]["u_start"] = 16
    assert parse(value).as_dict() == value
    for field in ("asset_ref", "incarnation_ref", "placement_ref"):
        changed = deepcopy(value)
        changed["nodes"][1]["registration"][field] = value["nodes"][0]["registration"][field]
        with pytest.raises(ContractError): parse(changed)
    for patch in ({"label": "Other rack"}, {"u_start": 15}):
        changed = deepcopy(value)
        changed["nodes"][1]["registration"]["rack"].update(patch)
        with pytest.raises(ContractError): parse(changed)


def test_placement_exact_operation_and_two_origins(tmp_path, monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    value = current_placement()
    with http_endpoint(issuer) as (portal, issued), http_endpoint(lambda *_: (200, value)) as (gateway, reads):
        config = profile(tmp_path, portal, gateway)
        for command in (["--site", "site-a", "jobs", "placement", "12345_0"],
                        ["jobs", "placement", "12345_0", "--site", "site-a", "--format", "table"]):
            result, output, error = invoke(config, tmp_path, [*command, "--scope", "project-account", "--account", "project-example"])
            assert result == 0, error
            assert ("Recorded locations" in output) if "table" in command else json.loads(output) == value
        value["allocation"]["job"]["array_task_id"] = "1"
        result, output, _ = invoke(config, tmp_path, ["jobs", "placement", "12345_0", "--scope", "project-account", "--account", "project-example"])
        assert result == 7 and output == ""
    assert len(issued) == 1 and issued[0]["body"]["operation"] == "jobs.placement"
    assert issued[0]["body"]["job_id"] == "12345_0" and issued[0]["body"]["limit"] is None
    assert all(call["path"] == "/v1/site-read/jobs/12345_0/placement" and call["bearer"] is None for call in reads)


@pytest.mark.parametrize("command", ["jobs", "runs"])
@pytest.mark.parametrize("output_format", ["json", "table"])
@pytest.mark.parametrize("expiry", ["inventory", "registration", "in-transit"])
def test_placement_expired_at_receipt_has_no_output_or_weaker_retry(tmp_path, monkeypatch, command, output_format, expiry):
    from test_run_placement import current_sample

    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")

    def response(*_):
        payload = current_sample() if command == "runs" else current_placement()
        value = payload["placement"] if command == "runs" else payload
        now = datetime.now(timezone.utc)
        utc = lambda delta: (now + timedelta(seconds=delta)).isoformat().replace("+00:00", "Z")
        value["allocation"]["freshness"]["observed_at"] = utc(-2)
        value["nodes"][0]["registration"]["valid_until"] = utc(.08 if expiry == "in-transit" else -1)
        if expiry == "inventory":
            value["inventory"]["expires_at"] = utc(-1)
        parse(value)  # The response is internally valid for its original observation.
        if expiry == "in-transit":
            time.sleep(.15)
        return 200, payload

    def portal_response(call, count):
        return issuer(call, count) if call["method"] == "POST" else response()

    with http_endpoint(portal_response) as (portal, issued), http_endpoint(response) as (gateway, reads):
        config = profile(tmp_path, portal, gateway)
        selectors = (["12345_0", "--scope", "project-account", "--account", "project-example"]
                     if command == "jobs" else ["run-example-1", "--workspace-key", "project:project-example"])
        result, output, error = invoke(config, tmp_path, [command, "placement", *selectors, "--format", output_format])
    assert result == 7 and output == ""
    if output_format == "json":
        assert json.loads(error)["error"]["code"] == "contract_invalid"
    else:
        assert error.startswith("ERROR [contract_invalid]:")
    assert len(issued) == 1 and len(reads) == (1 if command == "jobs" else 0)


@pytest.mark.parametrize("failure", ["wrong-operation", "source", "denied", "redirect"])
def test_placement_permission_and_source_errors_never_fallback(tmp_path, monkeypatch, failure):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    def issue(call, count):
        status, payload = issuer(call, count)
        if failure == "wrong-operation": payload["operation"] = "jobs.allocation"
        return status, payload
    with http_endpoint(issue) as (portal, issued), http_endpoint(
        lambda *_: ({"source": 503, "denied": 403, "redirect": 302}.get(failure, 200), {"private": "not-for-output"})
    ) as (gateway, reads):
        config = profile(tmp_path, portal, gateway)
        result, output, error = invoke(config, tmp_path, ["jobs", "placement", "12345"])
        assert result != 0 and output == "" and "not-for-output" not in error
    assert len(issued) == 1 and len(reads) == (0 if failure == "wrong-operation" else 1)
