from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import StringIO
import json
from pathlib import Path
import threading
import time
from typing import Any, Iterator
from urllib.parse import parse_qs, urlsplit

import pytest

from sai_cli.cli import main


class _Server(ThreadingHTTPServer):
    response_status = 200
    response_payload: dict[str, Any] = {}
    capability_payload: dict[str, Any] = {}
    requests: list[dict[str, Any]]


class _Handler(BaseHTTPRequestHandler):
    server: _Server

    def _respond(self, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(self.server.response_status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("X-Request-ID", "server-request-id")
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlsplit(self.path)
        self.server.requests.append(
            {
                "method": "GET",
                "path": parsed.path,
                "query": parse_qs(parsed.query),
                "authorization": self.headers.get("Authorization"),
                "capability": self.headers.get("X-SAI-Capability"),
                "request_id": self.headers.get("X-SAI-Request-ID"),
            }
        )
        self._respond(self.server.response_payload)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlsplit(self.path)
        content_length = int(self.headers.get("Content-Length") or 0)
        raw_body = self.rfile.read(content_length) if content_length else b""
        self.server.requests.append(
            {
                "method": "POST",
                "path": parsed.path,
                "query": parse_qs(parsed.query),
                "authorization": self.headers.get("Authorization"),
                "capability": self.headers.get("X-SAI-Capability"),
                "body": json.loads(raw_body) if raw_body else None,
                "request_id": self.headers.get("X-SAI-Request-ID"),
            }
        )
        payload = (
            self.server.capability_payload
            if parsed.path == "/v1/authz/site-read"
            else self.server.response_payload
        )
        self._respond(payload)

    def log_message(self, format: str, *args: object) -> None:
        return


@contextmanager
def _server(
    payload: dict[str, Any],
    *,
    status: int = 200,
    capability_payload: dict[str, Any] | None = None,
) -> Iterator[tuple[str, _Server]]:
    server = _Server(("127.0.0.1", 0), _Handler)
    server.response_payload = payload
    server.response_status = status
    server.capability_payload = capability_payload or {}
    server.requests = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}", server
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def _env(tmp_path: Path) -> dict[str, str]:
    return {
        "SAI_TOKEN": "test-bearer-token",
        "XDG_CONFIG_HOME": str(tmp_path / "config"),
        "XDG_CACHE_HOME": str(tmp_path / "cache"),
        "XDG_DATA_HOME": str(tmp_path / "data"),
    }


@pytest.mark.parametrize("name", ["SAI_API_USERNAME", "SAI_API_KEY_ID", "SAI_API_SHARED_SECRET"])
@pytest.mark.parametrize("managed", [False, True])
@pytest.mark.parametrize("value", ["", "retired-auth-value"])
def test_retired_authentication_environment_fails_before_any_request(
    tmp_path: Path, job_payload, name: str, managed: bool, value: str,
) -> None:
    output, errors = StringIO(), StringIO()
    env = {**_env(tmp_path), name: value, "SAI_MANAGED_LOGIN_NODE": str(int(managed))}
    with _server(job_payload) as (origin, server):
        result = main(["jobs", "list", "--base-url", origin, "--site", "site-a"],
                      environ=env, stdout=output, stderr=errors)
        assert server.requests == []
    assert result == 2 and output.getvalue() == ""
    assert json.loads(errors.getvalue())["error"]["code"] == "configuration_invalid"
    assert f"unset {name}, then run" in errors.getvalue()
    assert "sai auth login" in errors.getvalue() and "retired-auth-value" not in errors.getvalue()


def test_missing_identity_session_fails_before_any_request(tmp_path: Path, job_payload) -> None:
    output, errors = StringIO(), StringIO()
    env = _env(tmp_path)
    env.pop("SAI_TOKEN")
    with _server(job_payload) as (origin, server):
        result = main(["jobs", "list", "--base-url", origin, "--site", "site-a"],
                      environ=env, stdout=output, stderr=errors)
        assert server.requests == []
    assert result == 3 and output.getvalue() == ""
    assert json.loads(errors.getvalue())["error"]["code"] == "credentials_unavailable"
    assert "sai auth login" in errors.getvalue()


@pytest.mark.parametrize("selector", [
    ["--scope", "project-account", "--account", "project-example"],
    ["--workspace-key", "project:owner-example"],
    ["--scope", "project-account", "--workspace-key", "project:owner-example"],
])
def test_jobs_list_maps_scope_and_emits_allowlisted_json(tmp_path: Path, job_payload, selector) -> None:
    payload = deepcopy(job_payload)
    payload["scope"] = "project_account"
    payload["visibility_role"] = "read"
    payload["slurm_user"] = None
    payload["slurm_account"] = "project-example"
    payload["items"][0]["slurm_account"] = "project-example"
    payload["items"][0]["raw_json"] = {"token": "must-not-leak"}
    stdout = StringIO()
    stderr = StringIO()

    with _server(payload) as (base_url, server):
        result = main(
            [
                "jobs",
                "list",
                "--base-url",
                base_url,
                "--site",
                "site-a",
                *selector,
                "--states",
                "r,pd",
                "--partition",
                "gpu-standard",
            ],
            environ=_env(tmp_path),
            stdout=stdout,
            stderr=stderr,
        )

    assert result == 0
    assert stderr.getvalue() == ""
    rendered = json.loads(stdout.getvalue())
    assert rendered["scope"] == "project_account"
    assert "raw_json" not in rendered["items"][0]
    assert "must-not-leak" not in stdout.getvalue()
    request = server.requests[0]
    assert request["path"] == "/v1/slurm/jobs"
    assert request["authorization"] == "Bearer test-bearer-token"
    assert request["request_id"].startswith("sai-cli-")
    assert request["query"] == {
        "site_id": ["site-a"],
        "scope_type": ["project_account"],
        **({"workspace_key": ["project:owner-example"]} if "--workspace-key" in selector
           else {"slurm_account_name": ["project-example"]}),
        "states": ["PD,R"],
        "source_preference": ["live"],
        "partition": ["gpu-standard"],
        "limit": ["100"],
    }


def test_managed_capability_mode_uses_server_bound_cli_route(
    tmp_path: Path,
    job_payload,
) -> None:
    capability = {
        "schema_version": "sai-site-read-capability/v1",
        "capability": "opaque-capability-token",
        "expires_at": int(time.time()) + 120,
        "audience": "sai-site-read",
        "surface": "site-read",
        "operation": "jobs.list",
        "site_id": "site-a",
        "cluster_id": "cluster-a",
    }
    stdout = StringIO()
    stderr = StringIO()
    with _server(job_payload, capability_payload=capability) as (base_url, server):
        result = main(
            [
                "jobs",
                "list",
                "--base-url",
                base_url,
                "--site",
                "site-a",
                "--cluster",
                "cluster-a",
            ],
            environ={
                **_env(tmp_path),
                "SAI_REQUIRE_SITE_CAPABILITY": "1",
            },
            stdout=stdout,
            stderr=stderr,
        )

    assert result == 0
    assert stderr.getvalue() == ""
    assert [request["method"] for request in server.requests] == ["POST", "GET"]
    issuer_request, read_request = server.requests
    assert issuer_request["path"] == "/v1/authz/site-read"
    assert issuer_request["authorization"] == "Bearer test-bearer-token"
    assert issuer_request["body"] == {
        "operation": "jobs.list",
        "site_id": "site-a",
        "cluster_id": "cluster-a",
        "scope_type": "self",
        "slurm_account_id": None,
        "slurm_account_name": None,
        "partition": None,
        "states": [],
        "job_id": None,
        "limit": 100,
    }
    assert read_request["path"] == "/v1/slurm/cli/jobs"
    assert read_request["authorization"] == "Bearer test-bearer-token"
    assert read_request["capability"] == "opaque-capability-token"


def test_jobs_show_uses_detail_endpoint_and_table_output(tmp_path: Path, job_payload) -> None:
    stdout = StringIO()
    stderr = StringIO()

    with _server(job_payload) as (base_url, server):
        result = main(
            [
                "jobs",
                "show",
                "12345",
                "--base-url",
                base_url,
                "--site",
                "site-a",
                "--format",
                "table",
            ],
            environ=_env(tmp_path),
            stdout=stdout,
            stderr=stderr,
        )

    assert result == 0
    assert stderr.getvalue() == ""
    assert "simulation" in stdout.getvalue()
    assert "GPU is the GPU count per node." in stdout.getvalue()
    assert server.requests[0]["path"] == "/v1/slurm/jobs/12345"
    assert "partition" not in server.requests[0]["query"]
    assert "limit" not in server.requests[0]["query"]


def test_bounded_http_error_does_not_echo_raw_secret(tmp_path: Path) -> None:
    stdout = StringIO()
    stderr = StringIO()
    payload = {
        "detail": {
            "code": "site_agent_unavailable",
            "message": "token=raw-secret source at /home/private 192.168.1.2",  # public-scan: allow-test-vector
            "raw": {"password": "another-secret"},
        }
    }

    with _server(payload, status=502) as (base_url, _):
        result = main(
            ["jobs", "list", "--base-url", base_url, "--site", "site-a"],
            environ=_env(tmp_path),
            stdout=stdout,
            stderr=stderr,
        )

    assert result == 6
    assert stdout.getvalue() == ""
    rendered = json.loads(stderr.getvalue())
    assert rendered["error"]["code"] == "site_agent_unavailable"
    assert rendered["error"]["request_id"] == "server-request-id"
    assert "raw-secret" not in stderr.getvalue()
    assert "another-secret" not in stderr.getvalue()
    assert "/home/private" not in stderr.getvalue()  # public-scan: allow-test-vector
    assert "192.168.1.2" not in stderr.getvalue()  # public-scan: allow-test-vector


def test_invalid_response_returns_contract_error(tmp_path: Path, job_payload) -> None:
    payload = deepcopy(job_payload)
    payload["items"][0].pop("state")
    stdout = StringIO()
    stderr = StringIO()

    with _server(payload) as (base_url, _):
        result = main(
            ["jobs", "list", "--base-url", base_url, "--site", "site-a"],
            environ=_env(tmp_path),
            stdout=stdout,
            stderr=stderr,
        )

    assert result == 7
    assert stdout.getvalue() == ""
    assert json.loads(stderr.getvalue())["error"]["code"] == "contract_invalid"


def test_scope_validation_fails_before_network(tmp_path: Path) -> None:
    stdout = StringIO()
    stderr = StringIO()

    result = main(
        [
            "jobs",
            "list",
            "--base-url",
            "http://127.0.0.1:9",
            "--site",
            "site-a",
            "--scope",
            "project-account",
        ],
        environ=_env(tmp_path),
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 2
    assert "requires --workspace-key" in stderr.getvalue()


def test_jobs_cost_uses_independent_endpoint_and_allowlisted_json(
    tmp_path: Path,
    running_estimate_payload,
) -> None:
    payload = deepcopy(running_estimate_payload)
    payload["scope"] = "project_account"
    payload["visibility_role"] = "read"
    payload["slurm_user"] = None
    payload["slurm_account"] = "project-example"
    for item in payload["items"]:
        item["slurm_account"] = "project-example"
    payload["items"][0]["raw_scheduler"] = {"token": "must-not-leak"}
    stdout = StringIO()
    stderr = StringIO()

    with _server(payload) as (base_url, server):
        result = main(
            [
                "--site",
                "site-a",
                "jobs",
                "cost",
                "--base-url",
                base_url,
                "--scope",
                "project-account",
                "--account",
                "project-example",
                "--states",
                "r,pd",
                "--partition",
                "gpu-standard",
            ],
            environ=_env(tmp_path),
            stdout=stdout,
            stderr=stderr,
        )

    assert result == 0
    assert stderr.getvalue() == ""
    rendered = json.loads(stdout.getvalue())
    assert rendered["operation"] == "billing.running-estimate"
    assert rendered["final"] is False
    assert rendered["items"][1]["estimate_status"] == "not_started"
    assert rendered["items"][2]["estimate_status"] == "unavailable"
    assert "raw_scheduler" not in rendered["items"][0]
    assert "must-not-leak" not in stdout.getvalue()
    request = server.requests[0]
    assert request["path"] == "/v1/billing/running-estimates"
    assert request["authorization"] == "Bearer test-bearer-token"
    assert request["query"] == {
        "site_id": ["site-a"],
        "scope_type": ["project_account"],
        "slurm_account_name": ["project-example"],
        "states": ["PD,R"],
        "source_preference": ["live"],
        "partition": ["gpu-standard"],
    }


def test_jobs_cost_table_shows_pending_unavailable_and_stale_snapshot(
    tmp_path: Path,
    running_estimate_payload,
) -> None:
    payload = deepcopy(running_estimate_payload)
    payload["freshness"]["stale"] = True
    payload["freshness"]["age_seconds"] = payload["freshness"]["ttl_seconds"]
    stdout = StringIO()
    stderr = StringIO()

    with _server(payload) as (base_url, _):
        result = main(
            [
                "jobs",
                "cost",
                "--base-url",
                base_url,
                "--site",
                "site-a",
                "--format",
                "table",
            ],
            environ=_env(tmp_path),
            stdout=stdout,
            stderr=stderr,
        )

    assert result == 0
    assert stderr.getvalue() == ""
    assert "Stale: yes" in stdout.getvalue()
    assert "PENDING" in stdout.getvalue()
    assert "UNAVAILABLE" in stdout.getvalue()
    assert "snapshot-etag" in stdout.getvalue()
