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
