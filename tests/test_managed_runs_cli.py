from io import StringIO
import json
from pathlib import Path

import pytest

from sai_cli.cli import build_parser, main
from test_cli_integration import _env, _server


def payload(name):
    path = Path(__file__).resolve().parents[1] / "contracts/managed-runs/v1" / f"{name}.sample.json"
    return json.loads(path.read_text())


@pytest.mark.parametrize("command,sample_name,path,options,query", [
    ("list", "list", "/v1/compute/cli/runs", ["--limit", "50"], {"limit": ["50"]}),
    ("show", "detail", "/v1/compute/cli/runs/run-example-1", [], {}),
    ("logs", "log", "/v1/compute/cli/runs/run-example-1/logs", ["--max-bytes", "128"],
     {"stream": ["stdout"], "max_bytes": ["128"]}),
    ("files", "artifacts", "/v1/compute/cli/runs/run-example-1/artifacts", ["--limit", "100"], {"limit": ["100"]}),
])
@pytest.mark.parametrize("prefix", [True, False])
@pytest.mark.parametrize("kind", ["personal", "org", "project"])
def test_batch_reads_shared_contract_with_connection_options_in_both_positions(tmp_path, command, sample_name, path, options, query, prefix, kind):
    body = payload(sample_name)
    body["workspace_key"] = kind + ":account-example"
    with _server(body) as (origin, server):
        connection = ["--site", body["site_id"], "--base-url", origin]
        args = ["runs", command, *([] if command == "list" else ["run-example-1"]),
                "--workspace-key", body["workspace_key"], *options]
        output, errors = StringIO(), StringIO()
        result = main(connection + args if prefix else args + connection,
                      environ={**_env(tmp_path), "SAI_REQUIRE_SITE_CAPABILITY": "1"}, stdout=output, stderr=errors)
    assert result == 0, errors.getvalue()
    assert errors.getvalue() == ""
    assert json.loads(output.getvalue()) == body
    assert len(server.requests) == 1
    request = server.requests[0]
    assert request["path"] == path
    assert request["query"] == {"workspace_key": [body["workspace_key"]], "site_id": [body["site_id"]], **query}
    assert request["capability"] is None
    assert request["authorization"] == "Bearer test-bearer-token"


@pytest.mark.parametrize("command,sample_name", [("list", "list"), ("show", "detail"), ("files", "artifacts")])
def test_table_output_uses_current_contract_without_native_or_billing_inference(tmp_path, command, sample_name):
    body = payload(sample_name)
    with _server(body) as (origin, _):
        output, errors = StringIO(), StringIO()
        result = main(["runs", command, *([] if command == "list" else ["run-example-1"]),
                       "--workspace-key", body["workspace_key"], "--base-url", origin,
                       "--site", body["site_id"], "--format", "table"],
                      environ=_env(tmp_path), stdout=output, stderr=errors)
    assert result == 0, errors.getvalue()
    assert "simulation.py" in output.getvalue() if command != "files" else "energy result.txt" in output.getvalue()
    assert "CNY" not in output.getvalue()


@pytest.mark.parametrize("output_format", ["json", "table"])
def test_log_content_stays_exact_json_and_cannot_inject_terminal_controls(tmp_path, output_format):
    body = payload("log")
    body["content"] = "iteration\t2\n\x1b[2J\x9b31m[value]\n"
    body["next_cursor"] = f"log-stdout-{len(body['content'].encode('utf-8'))}"
    with _server(body) as (origin, _):
        output, errors = StringIO(), StringIO()
        result = main(["runs", "logs", "run-example-1", "--workspace-key", body["workspace_key"],
                       "--base-url", origin, "--site", body["site_id"], "--format", output_format],
                      environ=_env(tmp_path), stdout=output, stderr=errors)
    assert result == 0, errors.getvalue()
    assert "\x1b" not in output.getvalue() and "\x9b" not in output.getvalue()
    if output_format == "json":
        assert json.loads(output.getvalue())["content"] == body["content"]
    else:
        assert "iteration\t2\n" in output.getvalue() and "[value]" in output.getvalue()


@pytest.mark.parametrize("arguments", [
    ["--cluster", "other"], ["--workspace-key", "all:project-example"],
    ["--limit", "101"], ["--cursor", "../unsafe"],
])
def test_invalid_run_selectors_never_send_http(tmp_path, arguments):
    body = payload("list")
    with _server(body) as (origin, server):
        output, errors = StringIO(), StringIO()
        result = main(["runs", "list", "--workspace-key", body["workspace_key"],
                       "--base-url", origin, "--site", body["site_id"], *arguments],
                      environ=_env(tmp_path), stdout=output, stderr=errors)
    assert result == 2 and server.requests == [] and output.getvalue() == ""


def test_file_denial_is_a_bounded_error_without_partial_results(tmp_path):
    body = {"detail": {"code": "run_file_read_denied", "message": "Output directory is not readable", "private": "/provider-secret"}}
    with _server(body, status=403) as (origin, _):
        output, errors = StringIO(), StringIO()
        result = main(["runs", "files", "run-example-1", "--workspace-key", "project:project-example",
                       "--base-url", origin, "--site", "site-a"], environ=_env(tmp_path), stdout=output, stderr=errors)
    assert result == 4 and output.getvalue() == ""
    error = json.loads(errors.getvalue())["error"]
    assert error["code"] == "run_file_read_denied" and "provider-secret" not in errors.getvalue()


def test_tui_task_scope_is_explicit_and_independent_of_job_scope():
    args = build_parser().parse_args(["--site", "site-a", "tui", "--scope", "self", "--tasks-workspace-key", "project:project-example"])
    assert args.site == "site-a" and args.scope == "self" and args.tasks_workspace_key == "project:project-example"


@pytest.mark.parametrize("prefix", [True, False])
@pytest.mark.parametrize("kind", ["personal", "org", "project"])
def test_selected_artifact_content_uses_one_authorized_get_and_escapes_terminal(tmp_path, prefix, kind):
    body = json.loads((Path(__file__).resolve().parents[1] / "contracts/managed-run-content/v1/available.sample.json").read_text())
    body["workspace_key"] = kind + ":account-example"
    body["content"] = "<html>result</html>\n\x1b[31m"
    body["size_bytes"] = body["next_offset"] = body["bytes_read"] = len(body["content"].encode())
    for presentation in ["json", "table"]:
        with _server(body) as (origin, server):
            options = ["--base-url", origin, "--site", "site-a"]
            command = ["runs", "read", body["run_ref"], "--artifact-ref", body["artifact_ref"],
                       "--workspace-key", body["workspace_key"], "--format", presentation]
            out, err = StringIO(), StringIO()
            result = main(options + command if prefix else command + options,
                          environ=_env(tmp_path), stdout=out, stderr=err)
            assert result == 0, err.getvalue()
            assert len(server.requests) == 1 and server.requests[0]["path"].endswith("/content")
            assert server.requests[0]["query"] == {"workspace_key": [body["workspace_key"]], "site_id": ["site-a"]}
            assert "\x1b" not in out.getvalue()
            if presentation == "json": assert json.loads(out.getvalue()) == body
            else: assert "<html>result</html>" in out.getvalue()
