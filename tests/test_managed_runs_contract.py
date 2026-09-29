from copy import deepcopy
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from sai_cli.errors import ConfigError, ContractError
from sai_cli.managed_runs import ManagedRunList, ManagedRunDetail, ManagedRunLogs, ManagedRunArtifacts, clean_tasks_workspace, render_managed_runs


KINDS = {"list": ManagedRunList, "detail": ManagedRunDetail, "log": ManagedRunLogs, "artifacts": ManagedRunArtifacts}


def sample(kind):
    return json.loads((Path(__file__).resolve().parents[1] / "contracts/managed-runs/v1" / f"{kind}.sample.json").read_text())


def parse(kind, data=None, **changes):
    data = sample(kind) if data is None else data
    kwargs = dict(workspace_key="project:project-example", site_id="site-a", request_id="managed-read")
    if kind != "list": kwargs["run_ref"] = "run-example-1"
    if kind in {"list", "artifacts"}: kwargs.update(limit=100, cursor=None)
    if kind == "log": kwargs.update(stream="stdout", cursor=None, max_bytes=65536)
    return KINDS[kind].from_payload(data, **{**kwargs, **changes})


def test_run_web_link_preserves_exact_reference_and_only_the_portal_origin():
    data = sample("detail")
    data["run"]["run_ref"] = "run:example+1"
    result = parse("detail", data, run_ref="run:example+1")
    url = urlsplit(result.web_url("https://console.example.test/prefix?ignored=1#old"))
    assert (url.scheme, url.netloc, url.path, url.query) == ("https", "console.example.test", "/portal/", "")
    route, query = url.fragment.split("?", 1)
    assert route == "/portal/workspaces/project%3Aproject-example/site-a/runs"
    assert parse_qs(query) == {"run_ref": ["run:example+1"]}


@pytest.mark.parametrize("cursor", [None, "0", "7"])
def test_run_file_web_link_uses_selected_current_page_reference_and_request_cursor(cursor):
    detail = parse("detail")
    data = sample("artifacts")
    data.update(cursor=cursor or "0", next_cursor=str(int(cursor or "0") + 1), complete=False)
    data["items"][0].update(relative_path="outputs/训练 #1?%.txt", display_name="long Unicode result")
    page = parse("artifacts", data, cursor=cursor)
    reference = data["items"][0]["artifact_ref"]
    url = urlsplit(detail.web_url("https://console.example.test/prefix?ignored=1#old", artifact_page=page, artifact_ref=reference))
    assert (url.scheme, url.netloc, url.path, url.query) == ("https", "console.example.test", "/portal/", "")
    expected = {"run_ref": ["run-example-1"], "view": ["files"], "artifact_ref": [reference]}
    if cursor is not None: expected["artifact_cursor"] = [cursor]
    assert parse_qs(url.fragment.split("?", 1)[1]) == expected
    assert "next_cursor" not in url.fragment and "outputs" not in url.fragment and "size" not in url.fragment
    assert page.as_dict() == data and "request_cursor" not in page.as_dict()


def test_run_file_web_link_rejects_unbound_or_unlisted_artifact():
    detail, page = parse("detail"), parse("artifacts")
    ref = page.values["items"][0]["artifact_ref"]
    for arguments in ({"artifact_ref": ref}, {"artifact_page": page},
                      {"artifact_ref": ref, "artifact_page": page.as_dict()},
                      {"artifact_ref": "artifact-missing", "artifact_page": page},
                      {"artifact_ref": "outputs/result.txt", "artifact_page": page}):
        with pytest.raises(ConfigError): detail.web_url("https://console.example", **arguments)
    for field, wrong in (("run_ref", "run-other"), ("site_id", "site-other"),
                         ("workspace_key", "project:other"), ("cursor", "1")):
        changed = parse("artifacts")
        changed.values[field] = wrong
        with pytest.raises(ConfigError):
            detail.web_url("https://console.example", artifact_page=changed, artifact_ref=ref)


@pytest.mark.parametrize("kind", KINDS)
def test_shared_managed_run_vectors_are_required_allowlists_bound_to_request(kind):
    expected = sample(kind)
    data = deepcopy(expected)
    nested = [data]
    if kind == "list": nested += data["items"]
    if kind == "detail": nested += [data["run"]]
    if kind in {"log", "artifacts"}: nested += [data["freshness"]]
    if kind == "artifacts": nested += data["items"]
    for row in nested: row["hidden"] = {"wallet": "private", "script": "private", "absolute_path": "/private/value"}
    parsed = parse(kind, data)
    assert parsed.as_dict() == expected and "private" not in render_managed_runs(parsed)
    output = parsed.as_dict()
    output["site_id"] = "other"
    assert parsed.values["site_id"] == "site-a"
    for key in expected:
        invalid = deepcopy(expected)
        del invalid[key]
        with pytest.raises(ContractError): parse(kind, invalid)
    for context in ({"workspace_key": "project:other"}, {"site_id": "site-other"}):
        with pytest.raises(ContractError): parse(kind, **context)
    with pytest.raises(ContractError): parse(kind, {**expected, "site_id": "site+a"}, site_id="site+a")
    if kind != "list":
        with pytest.raises(ContractError): parse(kind, run_ref="another-run")


def test_run_records_preserve_terminal_unknowns_and_reject_invalid_metadata():
    data = sample("detail")
    for name in ("title", "scheduler_ref", "scheduler_state", "queued_at", "started_at", "finished_at", "last_observed_at", "error_code"):
        data["run"][name] = None
    assert parse("detail", data).as_dict() == data
    text = render_managed_runs(parse("detail", data))
    assert "completed" in text and "not live queue state" in text and "Not assigned" in text
    for key, invalid in (("run_ref", "bad/ref"), ("title", "/absolute/script.py"), ("title", "unsafe\x1b"), ("title", "unsafe\x7f"),
                         ("status", "gone"), ("state_revision", True), ("state_revision", 0),
                         ("cluster_id", "x" * 65), ("cluster_id", ".cluster"), ("scheduler_state", "x" * 65),
                         ("accepted_at", "2030-02-30T00:00:00Z"), ("error_code", "native private error")):
        changed = sample("detail")
        changed["run"][key] = invalid
        with pytest.raises(ContractError): parse("detail", changed)
    data = sample("detail")
    data["run"]["scheduler_state"] = "completed"
    data["run"]["title"] = " "
    data["run"]["cluster_id"] = "cluster:a"
    assert parse("detail", data).values["run"]["scheduler_state"] == "completed"
    assert parse("detail", data).values["run"]["cluster_id"] == "cluster:a"
    data["run"]["title"] = "train\x85part.sh"
    parsed = parse("detail", data)
    assert parsed.as_dict()["run"]["title"] == "train\x85part.sh"
    assert "train\\x85part.sh" in render_managed_runs(parsed) and "\x85" not in render_managed_runs(parsed)
    with pytest.raises(ConfigError): clean_tasks_workspace("project:example+other")


def test_run_list_cursor_is_real_run_identity_and_never_fabricates_pages():
    data = sample("list")
    data.update(has_more=True, next_cursor=data["items"][-1]["run_ref"])
    assert parse("list", data).as_dict() == data
    for mutate in (lambda p: p.update(next_cursor="other"), lambda p: p.update(items=[]),
                   lambda p: p.update(has_more=False), lambda p: p.update(items=p["items"] * 2)):
        changed = deepcopy(data); mutate(changed)
        with pytest.raises(ContractError): parse("list", changed)
    with pytest.raises(ContractError): parse("list", data, cursor=data["next_cursor"])
    with pytest.raises(ContractError): parse("list", sample("list"), cursor="run-example-1")


def test_log_cursor_matches_exact_utf8_bytes_and_control_characters_are_only_data():
    data = sample("log")
    data["content"] = "能量\n\t[red]\x1b]52;hidden\x07\r\x85"
    data["next_cursor"] = f"log-stdout-{len(data['content'].encode())}"
    parsed = parse("log", data)
    assert parsed.as_dict()["content"] == data["content"]
    text = render_managed_runs(parsed)
    assert "能量\n\t[red]\\x1b]52;hidden\\x07\\x0d\\x85" in text
    assert "\x1b" not in text and "\x07" not in text and "\x85" not in text
    for change in ({"next_cursor": "log-stderr-40"}, {"next_cursor": "log-stdout-1"}, {"cursor": "log-stdout-1"},
                   {"available": False}, {"content": "x" * 65537}, {"content": "\ud800"}, {"complete": False, "truncated": False},
                   {"freshness": {"source": "site-agent", "queried_at": "2030-01-01T00:07:00Z"}}):
        with pytest.raises(ContractError): parse("log", {**data, **change})
    with pytest.raises(ContractError): parse("log", data, max_bytes=1)
    data.update(available=False, content="", complete=False, truncated=False, next_cursor="log-stdout-0")
    assert "not available yet" in render_managed_runs(parse("log", data))
    with pytest.raises(ContractError): parse("log", {**data, "complete": True})


def test_artifact_paths_remain_filenames_and_file_pages_are_bounded():
    data = sample("artifacts")
    filename = "outputs/训练结果 #1?% +.txt\x85"
    data["items"][0].update(relative_path=filename, display_name=filename, modified_at_ns=2**64)
    parsed = parse("artifacts", data)
    assert parsed.as_dict() == data and "\\x85" in render_managed_runs(parsed)
    for field, value in (("relative_path", "/absolute"), ("relative_path", "outputs/../file"),
                         ("relative_path", "outputs\\file"), ("display_name", "line\nfile"),
                         ("relative_path", "x" * 1025), ("size_bytes", 2**63), ("size_bytes", True),
                         ("modified_at_ns", -1), ("kind", "directory")):
        changed = deepcopy(data); changed["items"][0][field] = value
        with pytest.raises(ContractError): parse("artifacts", changed)
    for change in ({"cursor": "1"}, {"complete": False}, {"next_cursor": "1"}, {"items": data["items"] * 101}):
        with pytest.raises(ContractError): parse("artifacts", {**data, **change})
    with pytest.raises(ContractError): parse("artifacts", data, cursor="1")
