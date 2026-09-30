from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from sai_cli.cli import main
from sai_cli.errors import ConfigError, ContractError
from sai_cli.run_stats import ManagedRunStats, render_run_stats
from test_cli_integration import _env, _server
from test_managed_runs_contract import parse as parse_run


def sample(name="available"):
    filename = name.replace("_", "-") + ".sample.json"
    return json.loads((Path(__file__).resolve().parents[1] / "contracts/managed-run-stats/v1" / filename).read_text())


def parse(data):
    return ManagedRunStats.from_payload(data, workspace_key="project:project-example", site_id="site-a",
                                        run_ref="run-example-1", request_id="stats")


@pytest.mark.parametrize("name", ["available", "not_running", "unavailable"])
def test_stats_shared_vectors_bind_scope_and_recursively_drop_unmodeled_fields(name):
    expected = sample(name)
    data = deepcopy(expected)
    for row in [data, *data["steps"], *([data["execution"]] if data["execution"] else [])]:
        row["private"] = {"uid": 1000, "path": "/sensitive-fixture", "raw": "native-secret"}
    assert parse(data).as_dict() == expected
    text = render_run_stats(parse(data))
    assert "sensitive-fixture" not in text and "native-secret" not in text
    assert "native sampling time unknown" in text
    if name != "available": assert "CPU seconds:" not in text and "RSS bytes:" not in text


def test_stats_preserve_zero_unknown_and_large_byte_strings_without_float_conversion():
    data = sample(); row = data["steps"][0]
    row.update(task_count=0, average_cpu_seconds=0, average_rss_bytes="0", maximum_task_rss_bytes="90071992547409931234")
    result = parse(data)
    assert result.as_dict() == data
    text = render_run_stats(result)
    assert "90071992547409931234" in text and "Mean cumulative CPU seconds: 0" in text
    assert "Mean cumulative CPU seconds: Unknown" in text


@pytest.mark.parametrize("field,value", [
    ("schema_version", "compute.run-stats/v2"), ("run_ref", "run-other"), ("workspace_key", "project:other"),
    ("site_id", "other"), ("source", "sacct"), ("status", []), ("status", "complete"),
    ("queried_at", "2030-02-30T00:00:00Z"), ("queried_at", "2030-01-01T00:00:00Z\n"),
    ("sampled_at", "2030-01-01T00:06:00Z"), ("read_started_at", None),
    ("read_started_at", "2030-01-01T00:06:01.000001Z"), ("read_finished_at", None),
    ("execution", None), ("steps", []),
])
def test_stats_reject_wrong_scope_source_window_and_state(field,value):
    data = sample(); data[field] = value
    with pytest.raises(ContractError): parse(data)


@pytest.mark.parametrize("field,value", [
    ("sluid", "s0000000000001\n"), ("sluid", "s000000000000i"), ("restart_count", True),
    ("restart_count", -1), ("restart_count", 9007199254740992),
    ("submit_time", None), ("start_time", "2030-13-01T00:00:00Z"), ("resize_time", "invalid"),
])
def test_stats_execution_is_typed_and_bounded(field,value):
    data=sample();data["execution"][field]=value
    with pytest.raises(ContractError):parse(data)


@pytest.mark.parametrize("field,value", [
    ("step_ref", "12345.batch\n"), ("step_ref", "012345.0"), ("step_ref", "12345.01"),
    ("step_ref", "12346.1"), ("step_ref", "12345_0.1"), ("step_ref", "12345.unknown"),
    ("nodes", []), ("nodes", ["compute-a", "compute-a"]), ("nodes", ["compute-a\n"]),
    ("task_count", True), ("task_count", 1.0), ("task_count", 9007199254740992),
    ("average_cpu_seconds", -1), ("average_cpu_seconds", 18446744073709551),
    ("average_rss_bytes", 0), ("average_rss_bytes", "01"), ("average_rss_bytes", "1e9"),
    ("maximum_task_rss_bytes", "1\n"), ("maximum_task_rss_bytes", "1" * 21),
])
def test_stats_steps_reject_ambiguity_sentinels_unsafe_values_and_implicit_units(field,value):
    data=sample();data["steps"][0][field]=value
    with pytest.raises(ContractError):parse(data)


def test_stats_null_combinations_missing_fields_duplicates_and_array_bounds():
    for key in sample():
        data=sample();del data[key]
        with pytest.raises(ContractError):parse(data)
    for section in ("execution", "steps"):
        for key in sample()[section] if section=="execution" else sample()[section][0]:
            data=sample();row=data[section] if section=="execution" else data[section][0];del row[key]
            with pytest.raises(ContractError):parse(data)
    for name in ("not_running", "unavailable"):
        for key,value in (("execution",sample()["execution"]),("steps",sample()["steps"]),("read_started_at","2030-01-01T00:07:00Z")):
            data=sample(name);data[key]=value
            with pytest.raises(ContractError):parse(data)
    for steps in ([sample()["steps"][0]]*2,[{**sample()["steps"][0],"step_ref":f"12345.{i}"} for i in range(65)]):
        data=sample();data["steps"]=steps
        with pytest.raises(ContractError):parse(data)
    data=sample();data["steps"][0]["nodes"]=[f"n{i}" for i in range(4097)]
    with pytest.raises(ContractError):parse(data)
    data=sample();data["read_started_at"]="2030-01-01T00:06:00.9Z";data["read_finished_at"]="2030-01-01T00:06:00.10Z"
    with pytest.raises(ContractError):parse(data)


@pytest.mark.parametrize("prefix",[True,False])
@pytest.mark.parametrize("output_format",["json","table"])
def test_stats_command_uses_only_exact_run_and_project_site_over_http(tmp_path,prefix,output_format):
    body=sample()
    with _server(body) as (origin,server):
        connection=["--site","site-a","--base-url",origin]
        command=["runs","stats","run-example-1","--workspace-key","project:project-example","--format",output_format]
        output,errors=StringIO(),StringIO()
        result=main(connection+command if prefix else command+connection,environ=_env(tmp_path),stdout=output,stderr=errors)
    assert result==0,errors.getvalue()
    assert len(server.requests)==1
    request=server.requests[0]
    assert request["path"]=="/v1/compute/cli/runs/run-example-1/stats"
    assert request["query"]=={"workspace_key":["project:project-example"],"site_id":["site-a"]}
    assert request["capability"] is None and request["authorization"]=="Bearer test-bearer-token"
    if output_format=="json":assert json.loads(output.getvalue())==body
    else:assert "Mean task RSS bytes: 1073741824" in output.getvalue()


@pytest.mark.parametrize("status,code,exit_code",[(403,"run_read_denied",4),(503,"run_stats_unavailable",6)])
def test_stats_failures_emit_no_partial_data_and_do_not_fallback(tmp_path,status,code,exit_code):
    with _server({"detail":{"code":code,"message":"Read unavailable","private":"sensitive-fixture"}},status=status) as (origin,server):
        output,errors=StringIO(),StringIO()
        result=main(["runs","stats","run-example-1","--workspace-key","project:project-example","--site","site-a","--base-url",origin],environ=_env(tmp_path),stdout=output,stderr=errors)
    assert result==exit_code and output.getvalue()=="" and len(server.requests)==1
    assert "sensitive-fixture" not in errors.getvalue()


def test_stats_deep_link_carries_one_mode_without_metrics_or_file_reference():
    detail=parse_run("detail")
    url=urlsplit(detail.web_url("https://console.example/prefix",stats=True))
    assert parse_qs(url.fragment.split("?",1)[1])=={"run_ref":["run-example-1"],"view":["stats"]}
    for options in ({"stats":"stats"},{"stats":True,"cost":True},{"stats":True,"artifact_ref":"artifact-x"},
                    {"stats":True,"artifact_page":parse_run("artifacts")}):
        with pytest.raises(ConfigError):detail.web_url("https://console.example",**options)
