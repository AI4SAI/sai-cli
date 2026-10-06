from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from sai_cli.catalog import ResourceCatalog
from sai_cli.errors import ConfigError

def document():
    data = json.loads((Path(__file__).resolve().parents[1] / "contracts/site-resource-catalog/v1/catalog.json").read_text())
    data["site_id"] = "site-a"
    data["compute"][0].update(
        title="科研 GPU 候选 [literal]", summary="完整用途说明：训练与科学模拟。" * 12,
        scenarios=["模型训练", "分子动力学"],
    )
    data["compute"][1].update(title="CPU 独立候选", summary="用于并行数据处理。", scenarios=["数据处理"])
    return data


def parsed(data=None):
    return ResourceCatalog.from_payload(document() if data is None else data, site_id="site-a", request_id="catalog")


def test_preparation_url_only_uses_current_site_and_one_exact_compute_candidate():
    url = urlsplit(parsed().preparation_url("https://console.example/prefix?ignored=1#old", "gpu-standard"))
    assert (url.scheme, url.netloc, url.path, url.query) == ("https", "console.example", "/portal/", "")
    route, query = url.fragment.split("?", 1)
    assert route == "/portal/resources/prepare"
    assert parse_qs(query) == {"site_id": ["site-a"], "partition_ref": ["gpu-standard"]}
    for reference in (None, "absent", "Project storage", "x" * 65, "gpu/standard", "gpu\nstandard"):
        with pytest.raises(ConfigError): parsed().preparation_url("https://console.example", reference)
    duplicate = document()
    duplicate["compute"].append(deepcopy(duplicate["compute"][0]))
    with pytest.raises(ConfigError): parsed(duplicate).preparation_url("https://console.example", "gpu-standard")
    wider = document()
    wider["compute"][0]["name"] = "x" * 65
    with pytest.raises(ConfigError): parsed(wider).preparation_url("https://console.example", "x" * 65)


@pytest.mark.parametrize("width", [40, 60, 100])
def test_comparison_columns_reflow_instead_of_truncating_facts(width):
    pytest.importorskip("textual")
    from rich.console import Console
    from sai_cli.tui_views import resource_panel
    data=document();output=StringIO()
    Console(file=output,width=width,color_system=None).print(resource_panel(None,data["compute"],"en-US",width))
    rendered=output.getvalue()
    assert "科研 GPU 候选 [literal]".replace(" ","") in "".join(rendered.split())
    assert "CPU 独立候选".replace(" ","") in "".join(rendered.split())
    assert "Unknown" in rendered and "QOS" in rendered and "normal" in rendered
