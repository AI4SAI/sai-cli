from __future__ import annotations

from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import StringIO
import json
from pathlib import Path
import threading
from unittest.mock import Mock

import pytest

from sai_cli.catalog import ResourceCatalog
from sai_cli.auth import TokenLease
from sai_cli.client import PortalClient
from sai_cli.cli import main
from sai_cli.errors import AuthenticationError, ContractError, ForbiddenError
from sai_cli.render import render_resource_catalog
from sai_cli.transport import JsonTransport
from test_cli_integration import _env, _server


FIXTURE = Path(__file__).resolve().parents[1] / "contracts/site-resource-catalog/v1/catalog.json"


@pytest.fixture
def catalog_payload():
    return json.loads(FIXTURE.read_text())


def parse(payload):
    return ResourceCatalog.from_payload(payload, site_id="site-example", request_id="catalog-test")


def test_shared_catalog_preserves_unknown_capacity_and_strips_nested_extras(catalog_payload):
    original = deepcopy(catalog_payload)
    catalog_payload["secret"] = "hidden"
    catalog_payload["compute"][0]["script"] = "hidden"
    catalog_payload["compute"][0]["pricing"]["wallet"] = "hidden"
    catalog_payload["storage"][0]["hardware"][0]["raw"] = "hidden"
    catalog_payload["storage"][0]["usage_pricing"]["token"] = "hidden"
    result = parse(catalog_payload)
    assert result.as_dict() == original
    assert result.as_dict()["compute"][1]["node_count"] is None
    table = render_resource_catalog(result)
    assert "unknown" in table
    assert "GPUs(total)" in table
    assert "Published specifications" in table
    assert "hidden" not in table
    assert "\t" not in table and "\r" not in table


@pytest.mark.parametrize(("path", "value"), [
    (("schema_version",), "site.resource-catalog/v2"),
    (("site_id",), "another-site"),
    (("compute", 0, "node_count"), True),
    (("compute", 0, "node_count"), -1),
    (("compute", 0, "gpu_count"), 9007199254740992),
    (("compute", 0, "resource_kind"), "unknown"),
    (("compute", 0, "name"), "has space"),
    (("compute", 0, "pricing", "unit_price"), "1e3"),
    (("compute", 0, "pricing", "unit_price"), "NaN"),
    (("compute", 0, "summary"), "bad\x1b[31m"),
    (("storage", 0, "hardware", 0, "value"), "bad\x9b"),
    (("storage", 0, "metered_settlement_enabled"), "false"),
    (("storage", 0, "scope_kind"), "all"),
    (("storage", 0, "package_pricing", "currency"), "USD"),
])
def test_catalog_rejects_malformed_or_wrong_site(catalog_payload, path, value):
    row = catalog_payload
    for part in path[:-1]:
        row = row[part]
    row[path[-1]] = value
    with pytest.raises(ContractError) as error:
        parse(catalog_payload)
    assert error.value.request_id == "catalog-test"


def test_catalog_requires_explicit_null_fields_and_bounds_lists(catalog_payload):
    missing = deepcopy(catalog_payload)
    del missing["compute"][0]["gpu_model"]
    with pytest.raises(ContractError):
        parse(missing)
    catalog_payload["compute"] *= 257
    with pytest.raises(ContractError):
        parse(catalog_payload)


@pytest.mark.parametrize("managed", [False, True])
@pytest.mark.parametrize("site_before", [False, True])
def test_catalog_http_uses_site_route_without_job_or_capability_request(
    tmp_path, catalog_payload, managed, site_before,
):
    output, errors = StringIO(), StringIO()
    with _server(catalog_payload) as (origin, server):
        args = ["--site", "site-example", "resources", "catalog"] if site_before else [
            "resources", "catalog", "--site", "site-example",
        ]
        result = main(
            [*args, "--base-url", origin],
            environ={**_env(tmp_path), "SAI_REQUIRE_SITE_CAPABILITY": "1" if managed else "0"},
            stdout=output, stderr=errors,
        )
    assert result == 0, errors.getvalue()
    assert json.loads(output.getvalue()) == catalog_payload
    assert len(server.requests) == 1
    request = server.requests[0]
    prefix = "/v1/account/cli/sites" if managed else "/v1/account/sites"
    assert request["path"] == f"{prefix}/site-example/resource-catalog"
    assert request["method"] == "GET" and request["query"] == {}
    assert request["capability"] is None
    assert request["authorization"] == "Bearer test-bearer-token"


def test_catalog_error_emits_no_partial_data_and_rejects_cluster_before_http(tmp_path, catalog_payload):
    output, errors = StringIO(), StringIO()
    with _server(catalog_payload, status=503) as (origin, server):
        args = ["resources", "catalog", "--site", "site-example", "--base-url", origin]
        result = main(args, environ=_env(tmp_path), stdout=output, stderr=errors)
        assert result == 6 and output.getvalue() == ""
        assert json.loads(errors.getvalue())["error"]
        before = len(server.requests)
        result = main([*args, "--cluster", "another-cluster"], environ=_env(tmp_path),
                      stdout=StringIO(), stderr=StringIO())
        assert result == 2 and len(server.requests) == before


def test_catalog_does_not_accept_account_scope():
    with pytest.raises(SystemExit) as error:
        main(["resources", "catalog", "--scope", "org-account", "--account", "org-example"])
    assert error.value.code == 2


@pytest.mark.parametrize(("source", "statuses", "error_type", "refreshes"), [
    ("cache", [401, 200], None, 1),
    ("cache", [401, 401], AuthenticationError, 1),
    ("environment", [401], AuthenticationError, 0),
    ("cache", [403], ForbiddenError, 0),
])
def test_catalog_http_refresh_is_bounded(catalog_payload, source, statuses, error_type, refreshes):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            status = statuses[len(requests)]
            requests.append((self.path, self.headers.get("X-SAI-Capability")))
            body = json.dumps(catalog_payload if status == 200 else {"detail": "denied"}).encode()
            self.send_response(status)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    provider = Mock()
    old = TokenLease(token="old-token", expires_at=None, source=source)
    provider.get.side_effect = [old, TokenLease(token="new-token", expires_at=None, source="exchange")]
    client = PortalClient(
        transport=JsonTransport(base_url=f"http://127.0.0.1:{server.server_port}", timeout_seconds=2),
        token_provider=provider,
        capability_provider=Mock(),
    )
    try:
        if error_type:
            with pytest.raises(error_type):
                client.resource_catalog("site-example")
        else:
            assert client.resource_catalog("site-example").as_dict() == catalog_payload
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
    assert len(requests) == len(statuses)
    assert all(path == "/v1/account/cli/sites/site-example/resource-catalog" and capability is None
               for path, capability in requests)
    assert provider.invalidate.call_count == refreshes
    assert provider.get.call_count == refreshes + 1
    if refreshes:
        provider.invalidate.assert_called_once_with(old)
        provider.get.assert_called_with(force_exchange=True)
    client.capability_provider.get.assert_not_called()
