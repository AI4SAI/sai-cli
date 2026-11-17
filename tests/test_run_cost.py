from copy import deepcopy
from io import StringIO
import json
from pathlib import Path

import pytest

from sai_cli.cli import main
from sai_cli.errors import ContractError
from sai_cli.run_cost import ManagedRunCost, render_run_cost
from test_cli_integration import _env, _server


def sample(name="settled"):
    return json.loads((Path(__file__).resolve().parents[1] / "contracts/managed-run-cost/v1" / f"{name}.sample.json").read_text())


def parse(data):
    return ManagedRunCost.from_payload(data, workspace_key="project:project-example", site_id="site-a",
                                       run_ref="run-example-1", request_id="cost")


def segmented_sample():
    body = sample()
    body['charge_amount'] = '140.00000000'
    body['amounts'].update(gross_amount='200.00000000', cash_amount='140.00000000',
        sai_credit_cny_equivalent_amount='0.00000000', sai_credit_amount='0.00000000',
        reservation_coverage_amount='0.00000000', price_adjustment_amount='60.00000000', quantity='100.00000000')
    body['segments'] = []
    for index, quantity, gross, cash, price, adjustment in [
        (0, '60.00000000', '120.00000000', '60.00000000', '1.00000000', '60.00000000'),
        (1, '40.00000000', '80.00000000', '80.00000000', '2.00000000', '0.00000000'),
    ]:
        body['segments'].append({'line_item_id': f'line-{index}', 'segment_index': index,
            'purchase_reference': 'purchase-a' if index == 0 else None,
            'pricing_contract_key': None, 'purchase_label': 'Purchase A' if index == 0 else None,
            'contract_no': None, 'quantity': quantity, 'unit_name': body['unit_name'],
            'unit_price': price, 'charge_amount': cash,
            'amounts': {**body['amounts'], 'gross_amount': gross, 'cash_amount': cash,
                'price_adjustment_amount': adjustment, 'quantity': quantity}})
    return body


def test_cost_purchase_segments_preserve_producer_values_and_redaction():
    body = segmented_sample()
    supplied = deepcopy(body)
    supplied['segments'][0]['private_source'] = 'never-show'
    supplied['segments'][1]['amounts']['private'] = 'never-show'
    assert parse(supplied).as_dict() == body
    rendered = render_run_cost(parse(supplied))
    assert 'Purchase A' in rendered and '140.00 CNY' in rendered
    assert '60.00 CNY' in rendered and '80.00 CNY' in rendered and 'never-show' not in rendered
    assert body['segments'][0]['segment_index'] == 0
    single = deepcopy(body)
    single['segments'] = single['segments'][:1]
    single['amounts'] = deepcopy(single['segments'][0]['amounts'])
    single['charge_amount'] = single['segments'][0]['charge_amount']
    assert parse(single).as_dict() == single
    hidden = deepcopy(body)
    hidden['cash_visible'] = False
    hidden['charge_amount'] = None
    from sai_cli.run_cost import FUNDING_FIELDS
    for key in FUNDING_FIELDS:
        hidden['amounts'][key] = None
    for row in hidden['segments']:
        for key in ('unit_price', 'charge_amount', 'purchase_reference', 'pricing_contract_key', 'purchase_label', 'contract_no'):
            row[key] = None
        for key in FUNDING_FIELDS:
            row['amounts'][key] = None
    assert parse(hidden).as_dict() == hidden
    assert 'Purchase A' not in render_run_cost(parse(hidden))
    for key, value in [('unit_price', '1.00000000'), ('charge_amount', '60.00000000'), ('purchase_label', 'Private purchase')]:
        invalid = deepcopy(hidden)
        invalid['segments'][0][key] = value
        with pytest.raises(ContractError):
            parse(invalid)
    pending = sample('pending')
    pending.update(charge_amount=None, segments=[])
    assert parse(pending).as_dict() == pending
    pending['segments'] = body['segments']
    with pytest.raises(ContractError):
        parse(pending)
    duplicate = deepcopy(body)
    duplicate['segments'][1]['line_item_id'] = duplicate['segments'][0]['line_item_id']
    with pytest.raises(ContractError):
        parse(duplicate)


@pytest.mark.parametrize("name", ["settled", "gross-only", "pending", "unavailable", "not_chargeable"])
def test_cost_shared_vectors_are_bound_allowlists_without_amount_inference(name):
    data = sample(name)
    source = deepcopy(data)
    source["wallet_id"] = "private-wallet"
    source["amounts"]["private"] = "provider-secret"
    assert parse(source).as_dict() == data
    text = render_run_cost(parse(source))
    assert "private-wallet" not in text and "provider-secret" not in text
    if data["status"] != "settled":
        assert "0.00000000" not in text and "Cash charged" not in text
    if not data["cash_visible"]:
        assert "10.00" in text and "Cash charged" not in text and "points" not in text


@pytest.mark.parametrize("field,value", [
    ("schema_version", "compute.run-cost/v2"), ("site_id", "other"), ("workspace_key", "project:other"),
    ("run_ref", "run-other"), ("source", "scheduler"), ("status", []), ("status", "completed"),
    ("currency", "USD"), ("cash_visible", 1), ("queried_at", "2030-02-30T00:00:00Z"),
    ("settled_at", "2030-01-01T00:00:00Z\n"), ("unit_name", "gpu\x1b"),
])
def test_cost_rejects_wrong_binding_and_malformed_facts(field, value):
    data = sample(); data[field] = value
    with pytest.raises(ContractError): parse(data)


@pytest.mark.parametrize("value", [0, True, "-1.00000000", "1", "01.00000000", "1e2", "NaN", "1.000000000", "1.00000000\n", "1" * 65, None])
def test_cost_money_is_exact_bounded_decimal_text(value):
    data = sample(); data["amounts"]["cash_amount"] = value
    with pytest.raises(ContractError): parse(data)


def test_cost_state_nulls_and_all_required_fields_fail_closed():
    for key in sample():
        data = sample(); del data[key]
        with pytest.raises(ContractError): parse(data)
    for key in sample()["amounts"]:
        data = sample(); del data["amounts"][key]
        with pytest.raises(ContractError): parse(data)
    for name in ("pending", "unavailable", "not_chargeable", "gross-only"):
        data = sample(name); data["amounts"]["cash_amount"] = "0.00000000"
        with pytest.raises(ContractError): parse(data)
    for field in ("unit_name", "settled_at"):
        data = sample("not_chargeable"); data[field] = sample()[field]
        with pytest.raises(ContractError): parse(data)
    data = sample(); data["settled_at"] = data["unit_name"] = None
    assert parse(data).as_dict() == data


def test_readable_final_cost_keeps_tiny_signed_adjustment_and_exact_json():
    from sai_cli.run_cost import cost_lines
    data = sample()
    data["amounts"].update(price_adjustment_amount="-0.00100000", quantity="0.12345678")
    result = parse(data)
    for language in ("zh-CN", "en-US"):
        text = "\n".join(cost_lines(result, language))
        assert "-0.001 CNY" in text and "0.1235" in text
        assert "10.00 CNY" in text and "400 " in text
        assert "10.00000000" not in text and "400.00000000" not in text
    assert result.as_dict() == data


@pytest.mark.parametrize("prefix", [True, False])
@pytest.mark.parametrize("output_format", ["json", "table"])
def test_cost_command_uses_exact_http_path_and_explicit_scope(tmp_path, prefix, output_format):
    body = sample()
    body["amounts"].update(cash_amount="7.20000000", price_adjustment_amount="-1.20000000")
    with _server(body) as (origin, server):
        connection = ["--site", "site-a", "--base-url", origin]
        command = ["runs", "cost", "run-example-1", "--workspace-key", "project:project-example", "--format", output_format]
        output, errors = StringIO(), StringIO()
        code = main(connection + command if prefix else command + connection,
                    environ=_env(tmp_path), stdout=output, stderr=errors)
    assert code == 0, errors.getvalue()
    assert len(server.requests) == 1 + (output_format == "table")
    if output_format == "table":
        assert server.requests[1]["path"] == "/v1/account/cli/sites/site-a/connection"
        assert server.requests[1]["authorization"] == "Bearer test-bearer-token"
        assert server.requests[1]["capability"] is None
    assert server.requests[0]["path"] == "/v1/compute/cli/runs/run-example-1/billing"
    assert server.requests[0]["query"] == {"site_id": ["site-a"], "workspace_key": ["project:project-example"]}
    assert server.requests[0]["capability"] is None
    if output_format == "json": assert json.loads(output.getvalue()) == body
    else:
        assert "Cash charged: 7.20 CNY" in output.getvalue() and "400 points" in output.getvalue()
        assert "-1.20 CNY" in output.getvalue()


@pytest.mark.parametrize("code", ["identity_scope_denied", "run_cost_read_denied", "run_read_denied"])
def test_cost_denial_is_bounded_and_does_not_fallback(tmp_path, code):
    with _server({"detail": {"code": code, "message": "Denied", "private": "sensitive-fixture"}}, status=403) as (origin, server):
        output, errors = StringIO(), StringIO()
        result = main(["runs", "cost", "run-example-1", "--workspace-key", "project:project-example", "--site", "site-a", "--base-url", origin],
                      environ=_env(tmp_path), stdout=output, stderr=errors)
    assert result == 4 and output.getvalue() == "" and len(server.requests) == 1
    assert json.loads(errors.getvalue())["error"]["code"] == code and "sensitive-fixture" not in errors.getvalue()


def test_cost_deep_link_selects_only_cost_and_rejects_file_mixing():
    from urllib.parse import parse_qs, urlsplit
    from sai_cli.errors import ConfigError
    from test_managed_runs_contract import parse as parse_run
    detail = parse_run("detail")
    link = urlsplit(detail.web_url("https://console.example/prefix", cost=True))
    assert link.path == "/portal/" and link.query == ""
    assert parse_qs(link.fragment.split("?", 1)[1]) == {"run_ref": ["run-example-1"], "view": ["cost"]}
    for kwargs in ({"cost": "cost"}, {"cost": True, "artifact_ref": "artifact-any"},
                   {"cost": True, "artifact_page": parse_run("artifacts")}):
        with pytest.raises(ConfigError): detail.web_url("https://console.example", **kwargs)
