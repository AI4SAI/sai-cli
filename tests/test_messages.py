"""Shared output language preserves the authorized facts."""
from copy import deepcopy
from string import Formatter

import pytest

from sai_cli.messages import MESSAGES, Messages
from sai_cli.overview import AccountOverview
from sai_cli.overview_view import overview_rows
from test_overview import sample


def test_languages_have_the_same_fields():
    for key, pair in MESSAGES.items():
        assert len(pair) == 2 and all(pair)
        fields = [{field for _, field, _, _ in Formatter().parse(value) if field} for value in pair]
        assert fields[0] == fields[1], key
        for language in ("zh-CN", "en-US"):
            assert Messages(language)(key, **{field: "example" for field in fields[0]})


@pytest.mark.parametrize("state", ["available", "not_authorized", "unavailable"])
def test_overview_languages_preserve_funds_visibility(state):
    data = sample()
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
        key = "funds_denied" if state == "not_authorized" else "funds_unavailable"
        assert Messages("zh-CN")(key) in str(zh)
        assert Messages("en-US")(key) in str(en)
