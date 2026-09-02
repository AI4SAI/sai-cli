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

from sai_cli.cli import main


class _Server(ThreadingHTTPServer):
    response_status = 200
    response_payload: dict[str, Any] = {}
    requests: list[dict[str, Any]]


class _Handler(BaseHTTPRequestHandler):
    server: _Server

    def _handle(self) -> None:
        parsed = urlsplit(self.path)
        content_length = int(self.headers.get("Content-Length") or 0)
        raw_body = self.rfile.read(content_length) if content_length else b""
        self.server.requests.append(
            {
                "method": self.command,
                "path": parsed.path,
                "query": parse_qs(parsed.query),
                "authorization": self.headers.get("Authorization"),
                "capability": self.headers.get("X-SAI-Capability"),
                "content_type": self.headers.get("Content-Type"),
                "body": json.loads(raw_body) if raw_body else None,
                "request_id": self.headers.get("X-SAI-Request-ID"),
            }
        )
        encoded = json.dumps(self.server.response_payload).encode("utf-8")
        self.send_response(self.server.response_status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("X-Request-ID", "server-request-id")
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:  # noqa: N802
        self._handle()

    def do_POST(self) -> None:  # noqa: N802
        self._handle()

    def log_message(self, format: str, *args: object) -> None:
        return


@contextmanager
def _server(
    payload: dict[str, Any],
    *,
    status: int = 200,
) -> Iterator[tuple[str, _Server]]:
    server = _Server(("127.0.0.1", 0), _Handler)
    server.response_payload = payload
    server.response_status = status
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
    }


def _capability_payload(*, operation: str = "jobs.list") -> dict[str, object]:
    return {
        "schema_version": "sai-site-read-capability/v1",
        "capability": "opaque-capability-token",
        "expires_at": int(time.time()) + 120,
        "audience": "sai-site-read",
        "surface": "site-read",
        "operation": operation,
        "site_id": "site-a",
        "cluster_id": "cluster-a",
    }


def _connection_args(portal_url: str, site_read_url: str) -> list[str]:
    return [
        "--base-url",
        portal_url,
        "--site-read-base-url",
        site_read_url,
        "--site",
        "site-a",
    ]


def test_jobs_list_uses_post_issuer_and_capability_only_gateway(
    tmp_path: Path,
    job_payload,
) -> None:
    payload = deepcopy(job_payload)
    payload["scope_type"] = "project_account"
    payload["subject"] = {
        "slurm_user": None,
        "slurm_account": "project-example",
    }
    payload["items"][0]["slurm_account"] = "project-example"
    payload["items"][0]["raw_json"] = {"token": "must-not-leak"}
    stdout = StringIO()
    stderr = StringIO()

    with _server(_capability_payload()) as (portal_url, portal), _server(
        payload
    ) as (site_read_url, gateway):
        result = main(
            [
                *_connection_args(portal_url, site_read_url),
                "jobs",
                "list",
                "--cluster",
                "cluster-a",
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
    assert "raw_json" not in json.loads(stdout.getvalue())["items"][0]
    assert portal.requests[0]["method"] == "POST"
    assert portal.requests[0]["path"] == "/v1/authz/site-read"
    assert portal.requests[0]["authorization"] == "Bearer test-bearer-token"
    assert portal.requests[0]["capability"] is None
    assert portal.requests[0]["content_type"] == "application/json"
    assert portal.requests[0]["body"] == {
        "operation": "jobs.list",
        "site_id": "site-a",
        "cluster_id": "cluster-a",
        "scope_type": "project_account",
        "slurm_account_id": None,
        "slurm_account_name": "project-example",
        "partition": "gpu-standard",
        "states": ["PD", "R"],
        "job_id": None,
        "limit": 100,
    }
    assert gateway.requests == [
        {
            "method": "GET",
            "path": "/v1/site-read/jobs",
            "query": {},
            "authorization": None,
            "capability": "opaque-capability-token",
            "content_type": None,
            "body": None,
            "request_id": gateway.requests[0]["request_id"],
        }
    ]


def test_jobs_show_uses_exact_detail_capability_and_table(
    tmp_path: Path,
    job_payload,
) -> None:
    stdout = StringIO()
    stderr = StringIO()

    with _server(_capability_payload(operation="jobs.detail")) as (
        portal_url,
        portal,
    ), _server(job_payload) as (site_read_url, gateway):
        result = main(
            [
                *_connection_args(portal_url, site_read_url),
                "jobs",
                "show",
                "12345",
                "--cluster",
                "cluster-a",
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
    assert portal.requests[0]["body"]["job_id"] == "12345"
    assert portal.requests[0]["body"]["partition"] is None
    assert portal.requests[0]["body"]["limit"] is None
    assert gateway.requests[0]["path"] == "/v1/site-read/jobs/12345"


def test_gateway_error_is_bounded_without_portal_bearer(
    tmp_path: Path,
) -> None:
    stdout = StringIO()
    stderr = StringIO()
    error = {
        "detail": {
            "code": "site_read_unavailable",
            "message": "token=raw-secret source at /home/private 192.168.1.2",  # public-scan: allow-test-vector
            "raw": {"password": "another-secret"},
        }
    }

    with _server(_capability_payload()) as (portal_url, _portal), _server(
        error,
        status=502,
    ) as (site_read_url, gateway):
        result = main(
            [
                *_connection_args(portal_url, site_read_url),
                "jobs",
                "list",
                "--cluster",
                "cluster-a",
            ],
            environ=_env(tmp_path),
            stdout=stdout,
            stderr=stderr,
        )

    assert result == 6
    assert stdout.getvalue() == ""
    assert "raw-secret" not in stderr.getvalue()
    assert "another-secret" not in stderr.getvalue()
    assert gateway.requests[0]["authorization"] is None


def test_scope_validation_fails_before_network(tmp_path: Path) -> None:
    stdout = StringIO()
    stderr = StringIO()

    result = main(
        [
            *_connection_args("http://127.0.0.1:9", "http://127.0.0.1:10"),
            "jobs",
            "list",
            "--cluster",
            "cluster-a",
            "--scope",
            "project-account",
        ],
        environ=_env(tmp_path),
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 2
    assert "requires --account" in stderr.getvalue()


def test_jobs_cost_uses_running_operation_and_gateway_path(
    tmp_path: Path,
    running_estimate_payload,
) -> None:
    payload = deepcopy(running_estimate_payload)
    payload["scope_type"] = "project_account"
    payload["subject"] = {
        "slurm_user": None,
        "slurm_account": "project-example",
    }
    for item in payload["items"]:
        item["slurm_account"] = "project-example"
    payload["items"][0]["raw_scheduler"] = {"token": "must-not-leak"}
    stdout = StringIO()
    stderr = StringIO()

    with _server(_capability_payload(operation="billing.running-estimate")) as (
        portal_url,
        portal,
    ), _server(payload) as (site_read_url, gateway):
        result = main(
            [
                *_connection_args(portal_url, site_read_url),
                "jobs",
                "cost",
                "--cluster",
                "cluster-a",
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
    assert json.loads(stdout.getvalue())["final"] is False
    assert portal.requests[0]["body"]["operation"] == "billing.running-estimate"
    assert portal.requests[0]["body"]["limit"] is None
    assert gateway.requests[0]["path"] == (
        "/v1/site-read/billing/running-estimates"
    )
    assert gateway.requests[0]["authorization"] is None


def test_jobs_cost_table_preserves_freshness_states(
    tmp_path: Path,
    running_estimate_payload,
) -> None:
    payload = deepcopy(running_estimate_payload)
    payload["freshness"]["stale"] = True
    stdout = StringIO()
    stderr = StringIO()

    with _server(_capability_payload(operation="billing.running-estimate")) as (
        portal_url,
        _portal,
    ), _server(payload) as (site_read_url, _gateway):
        result = main(
            [
                *_connection_args(portal_url, site_read_url),
                "jobs",
                "cost",
                "--cluster",
                "cluster-a",
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
