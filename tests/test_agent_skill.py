"""Shipped guidance must remain usable before configuration or authorization."""

from io import StringIO
import json

import pytest

from sai_cli import __version__
from sai_cli.cli import main


def test_skill_is_offline_with_unusable_configuration_and_no_credentials(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("bundled skill initialized a provider")

    monkeypatch.setattr("sai_cli.config.resolve_settings", forbidden)
    monkeypatch.setattr("sai_cli.cli._build_transport", forbidden)
    monkeypatch.setattr("sai_cli.native_process.read_native_json", forbidden)
    output, errors = StringIO(), StringIO()
    env = {"SAI_CONFIG": str(tmp_path / "absent"), "SAI_TOKEN": "private-test-value",
           "SAI_MANAGED_LOGIN_NODE": "1", "PATH": ""}
    assert main(["skill"], environ=env, stdout=output, stderr=errors) == 0
    payload = json.loads(output.getvalue())
    assert payload["schema_version"] == "cli.skill/v1"
    assert payload["client_version"] == __version__ and payload["name"] == "sai-cli"
    assert "private-test-value" not in output.getvalue() and str(tmp_path) not in output.getvalue()
    assert not errors.getvalue() and not list(tmp_path.iterdir())

    markdown = StringIO()
    assert main(["skill", "--format", "markdown"], environ=env, stdout=markdown, stderr=errors) == 0
    assert markdown.getvalue() == payload["content"]
    assert markdown.getvalue().startswith("---\nname: sai-cli\n")


def test_skill_export_is_discoverable_as_non_mutating_client_operation():
    output, errors = StringIO(), StringIO()
    assert main(["describe", "skill"], environ={}, stdout=output, stderr=errors) == 0
    operation = json.loads(output.getvalue())["operations"][0]
    assert operation["source"] == "client" and operation["effect"] == "introspection"
    assert not operation["required_scopes"] and not operation["site_required"]
    assert {row["name"] for row in operation["parameters"]} == {"format"}
    assert operation["parameters"][0]["choices"] == ["json", "markdown"]
    assert not errors.getvalue()
