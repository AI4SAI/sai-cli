from io import StringIO
import importlib.util
import json

import pytest

from sai_cli.cli import build_parser, main


@pytest.mark.parametrize("args", [
    ["--site", "site-a", "tui", "--scope", "org-account", "--account", "org-example"],
    ["tui", "--site", "site-a", "--scope", "org-account", "--account", "org-example"],
])
def test_tui_connection_options_keep_documented_order(args):
    parsed = build_parser().parse_args(args)
    assert parsed.site == "site-a" and parsed.account == "org-example"


def test_tui_entry_fails_cleanly_for_missing_extra_or_non_terminal(tmp_path):
    output, errors = StringIO(), StringIO()
    code = main(["tui", "--site", "site-a", "--base-url", "https://portal.example.org"],
                environ={"XDG_CONFIG_HOME": str(tmp_path)}, stdout=output, stderr=errors)
    assert code == 2 and output.getvalue() == ""
    error = json.loads(errors.getvalue())["error"]
    expected = "interactive terminal" if importlib.util.find_spec("textual") else "sai-cli[tui]"
    assert expected in error["message"]


def test_actual_tui_command_opens_work_without_scope_input(tmp_path, job_payload, monkeypatch):
    pytest.importorskip("textual")
    import asyncio
    import sys
    from textual.widgets import Input
    from sai_cli.workbench import Workbench
    from test_site_transport import http_endpoint
    from test_workbench_flow import ResearchHTTP, settled

    class Terminal(StringIO):
        def isatty(self):
            return True

    async def inspect(app):
        async with app.run_test(size=(60, 24)) as pilot:
            await settled(app, pilot)
            assert app.mode == "home" and len(app.home_items) == 3
            assert len(app.query(Input)) == 0
            assert app.job_query.workspace_key is None

    monkeypatch.setattr(sys, "stdin", Terminal())
    monkeypatch.setattr(Workbench, "run", lambda app: asyncio.run(inspect(app)))
    output, errors = Terminal(), StringIO()
    with http_endpoint(ResearchHTTP(job_payload)) as (origin, calls):
        code = main(["tui", "--site", "site-a", "--base-url", origin],
            environ={"XDG_CONFIG_HOME": str(tmp_path), "SAI_TOKEN": "fixture-token"},
            stdout=output, stderr=errors)
    assert code == 0 and not errors.getvalue()
    assert len(calls) == 2
