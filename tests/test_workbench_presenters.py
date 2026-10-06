"""Readable evidence survives the workbench interaction replacement."""
from copy import deepcopy
from io import StringIO
from string import Formatter

import pytest
pytest.importorskip("textual")
from rich.console import Console
from sai_cli.managed_runs import ManagedRunArtifacts
from sai_cli.overview import AccountOverview
from sai_cli.overview_view import overview_rows
from sai_cli.site_jobs import SiteJobAllocationResult
from sai_cli.site_placement import SiteJobPlacementResult
from sai_cli.tui_messages import MESSAGES, Messages
from sai_cli.tui_views import allocation_panel, task_file_panel, modified_time_text, placement_panel
from sai_cli.workbench_copy import COPY, WorkbenchText
from test_managed_runs_contract import sample
from test_site_placement import sample as placement_sample
from test_overview import sample as overview_sample


@pytest.mark.parametrize("language", ["zh-CN", "en-US"])
@pytest.mark.parametrize("width", [40, 60, 100])
def test_allocation_panel_keeps_gres_units_indices_and_unknown_readable(site_allocation_payload, language, width):
    site_allocation_payload["allocation"]["nodes"][1]["gres"] = [
        {"name": "gpu", "type": "example", "count": 4, "indices": [0, 1, 2, 7]},
        {"name": "mps", "type": None, "count": 100, "indices": None},
        {"name": "shard", "type": None, "count": 0, "indices": None},
    ]
    result = SiteJobAllocationResult.from_payload(site_allocation_payload, request_id="panel")
    output = StringIO()
    Console(file=output, width=width, color_system=None).print(allocation_panel(result, language))
    text = output.getvalue()
    for expected in ("compute-a", "compute-b", "gpu:example", "mps", "shard", "0-2, 7",
                     "数量 100" if language == "zh-CN" else "Count 100",
                     "数量 0" if language == "zh-CN" else "Count 0",
                     "未知" if language == "zh-CN" else "Unknown"):
        assert expected in text
    assert ("Slurm 索引" if language == "zh-CN" else "Slurm indices") in text
    assert "CUDA/NVML" in text


def test_output_panel_preserves_full_paths_and_formats_mtime_without_losing_json_precision():
    data = sample("artifacts")
    path = "outputs/long-name-without-word-breaks-" + "result" * 9 + " #1.txt\x85"
    data["items"][0].update(relative_path=path, display_name="Friendly name")
    page = ManagedRunArtifacts.from_payload(data, workspace_key=data["workspace_key"], site_id=data["site_id"],
        run_ref=data["run_ref"], cursor=None, limit=100, request_id="files")
    output = StringIO()
    Console(file=output, width=38, color_system=None).print(task_file_panel(page))
    rendered = output.getvalue()
    assert "…" not in rendered and "Friendly name" not in rendered
    assert path.replace("\x85", "\\x85").replace(" ", "") in "".join(rendered.split())
    assert "Modified UTC: 2030-01-01 00:05:00" in rendered
    assert page.as_dict()["items"][0]["modified_at_ns"] == 1893456300000000001
    assert modified_time_text(0) == "Modified UTC: 1970-01-01 00:00:00"
    assert modified_time_text(10**30) == f"Modified: {10**30} ns since Unix epoch (outside calendar range)"


@pytest.mark.parametrize("language", ["zh-CN", "en-US"])
@pytest.mark.parametrize("width", [40, 60, 100])
def test_registered_location_panel_has_readable_units_and_verification_time(language, width):
    output = StringIO()
    result = SiteJobPlacementResult.from_payload(placement_sample(), request_id="panel")
    Console(file=output, width=width, color_system=None).print(placement_panel(result, language))
    text = output.getvalue()
    for expected in ("node-a", "Rack A", "U12", "4U", "2026-09-22T20:00:00Z",
                     "核对时间" if language == "zh-CN" else "Verified"):
        assert expected in text


def test_tiny_positive_cost_and_usage_never_render_as_zero(job_cost_payload):
    from sai_cli.contracts import JobCostResult
    from sai_cli.tui_views import job_cost_panel
    item = job_cost_payload["items"][0]["running_estimate"]
    item.update(gross_cny="0.00000001", cash_before_credit_cny="0.00000001")
    item["resources"]["usage_quantity"] = "0.00000001"
    for language in ("zh-CN", "en-US"):
        output = StringIO()
        Console(file=output, width=100, color_system=None).print(job_cost_panel(JobCostResult.from_payload(job_cost_payload, request_id="small"), language))
        text = output.getvalue()
        assert text.count("0.00000001 CNY") == 2 and "0.00000001" in text
    item.update(gross_cny="0.00000000", cash_before_credit_cny="0.00000000")
    item["resources"]["usage_quantity"] = "0.00000000"
    output = StringIO()
    Console(file=output, width=100).print(job_cost_panel(JobCostResult.from_payload(job_cost_payload, request_id="zero")))
    assert output.getvalue().count("0.00 CNY") == 2 and "<0.01" not in output.getvalue()


def test_language_catalog_placeholders_and_overview_financial_branches_agree():
    for key, pair in (MESSAGES | COPY).items():
        assert len(pair) == 2 and all(pair)
        fields = [{field for _, field, _, _ in Formatter().parse(value) if field} for value in pair]
        assert fields[0] == fields[1], key
        for language in ("zh-CN", "en-US"):
            assert WorkbenchText(language)(key, **{field: "example" for field in fields[0]})
    for state in ("available", "not_authorized", "unavailable"):
        data = overview_sample()
        if state != "available":
            data["funds"] = {key: state if key == "state" else value if key == "currency" else None
                             for key, value in data["funds"].items()}
        result = AccountOverview.from_payload(data, site_id="site-a", request_id="language")
        before = deepcopy(result.values)
        zh = overview_rows(result, language="zh-CN")
        en = overview_rows(result, language="en-US")
        assert [row[2] for row in zh] == [row[2] for row in en]
        assert result.values == before
        if state == "available":
            for amount in ("¥1,280.50", "20,000"):
                assert amount in str(zh) and amount in str(en)
        else:
            assert "¥0" not in str(zh) + str(en)
            assert Messages("zh-CN")("funds_denied" if state == "not_authorized" else "funds_unavailable") in str(zh)
            assert Messages("en-US")("funds_denied" if state == "not_authorized" else "funds_unavailable") in str(en)
