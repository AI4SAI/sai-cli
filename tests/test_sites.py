from copy import deepcopy
from io import StringIO
import json
import shlex
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from sai_cli.cli import main
from sai_cli.errors import ConfigError, ContractError
from sai_cli.sites import SiteDirectory, render_sites
from test_site_transport import http_endpoint


def sample():
    path = Path(__file__).resolve().parents[1] / "contracts/site-directory/v1/sample.json"
    return json.loads(path.read_text())


def parse(payload, **query):
    return SiteDirectory.from_payload(payload, limit=query.get("limit", 50),
                                      cursor=query.get("cursor"), request_id="test-request")


@pytest.mark.parametrize("prefix", [True, False])
def test_site_directory_works_before_site_selection_over_real_http(tmp_path, prefix):
    body = sample()
    def reply(call, number):
        assert number == 1 and call["method"] == "GET"
        assert call["bearer"] == "Bearer test-user" and call["capability"] is None
        split = urlsplit(call["path"])
        assert split.path == "/v1/account/cli/sites" and parse_qs(split.query) == {"limit": ["50"]}
        return 200, body
    with http_endpoint(reply) as (origin, calls):
        env = {"SAI_TOKEN": "test-user", "XDG_CONFIG_HOME": str(tmp_path / "missing"),
               "SAI_REQUIRE_SITE_CAPABILITY": "true", "PATH": ""}
        out, err = StringIO(), StringIO()
        args = ["--base-url", origin, "sites"] if prefix else ["sites", "--base-url", origin]
        assert main(args, environ=env, stdout=out, stderr=err) == 0, err.getvalue()
        assert json.loads(out.getvalue()) == body and len(calls) == 1
        assert not (tmp_path / "missing").exists()


def test_page_binding_and_allowlist_preserve_unicode_names():
    body = sample()
    body["items"][0].update(ssh_host="private-host", token="never-output", access=True)
    body["gateway_url"] = "https://private.example.org"
    result = parse(body)
    assert "private" not in json.dumps(result.as_dict()) and "never-output" not in json.dumps(result.as_dict())
    assert "研究站点" in render_sites(result)
    invalid = deepcopy(body)
    invalid["items"].append(invalid["items"][0])
    invalid["count"] = 2
    with pytest.raises(ContractError): parse(invalid)
    for field, value in (("count", 2), ("has_more", True), ("next_cursor", "site-z")):
        invalid = deepcopy(body); invalid[field] = value
        with pytest.raises(ContractError): parse(invalid)
    for field, value in (("display_name", "bad\x1b[31m"), ("site_id", "global")):
        invalid = deepcopy(body); invalid["items"][0][field] = value
        with pytest.raises(ContractError): parse(invalid)
    with pytest.raises(ContractError): parse(body, cursor="site-z")
    more = deepcopy(body);more.update(has_more=True, next_cursor=body["items"][-1]["site_id"])
    assert "Next: sai sites --cursor" in render_sites(parse(more))


def test_sites_rejects_explicit_site_and_propagates_denial_without_fallback(tmp_path):
    with http_endpoint(lambda *_: (403, {"detail": {"code": "identity_scope_denied", "raw": "never-output"}})) as (origin, calls):
        env = {"SAI_API_BASE_URL": origin, "SAI_TOKEN": "test-user", "XDG_CONFIG_HOME": str(tmp_path / "missing")}
        for invalid in (["--site", "site-a"], ["--limit", "101"], ["--cursor", "global"]):
            out, err = StringIO(), StringIO()
            assert main(["sites", *invalid], environ=env, stdout=out, stderr=err) == 2
            assert not out.getvalue() and not calls
        out, err = StringIO(), StringIO()
        assert main(["sites"], environ=env, stdout=out, stderr=err) == 4
        assert len(calls) == 1 and not out.getvalue()
        assert "identity_scope_denied" in err.getvalue() and "never-output" not in err.getvalue()


def test_site_connection_preserves_pinned_origin_cluster_constraints_and_https(tmp_path):
    from dataclasses import replace
    from sai_cli.config import Settings
    from sai_cli.sites import SiteConnection, resolve_site_settings
    settings = Settings(base_url='https://portal.example.org', site_id='site-a', timeout_seconds=5,
                        allow_insecure_http=False, cache_path=tmp_path/'cache', use_cache=True, profile='default')
    value = {'schema_version':'site.connection/v1', 'site_id':'site-a', 'cluster_id':'cluster-a',
             'site_read_base_url':'http://127.0.0.1:9180'}
    connection = SiteConnection.from_payload(value, site_id='site-a', request_id='test')
    with pytest.raises(ContractError): resolve_site_settings(settings, connection, gateway=True)
    pinned = replace(settings, site_read_base_url='https://pinned.example.org')
    assert resolve_site_settings(pinned, connection, gateway=True).site_read_base_url == pinned.site_read_base_url
    with pytest.raises(ConfigError): resolve_site_settings(replace(pinned, cluster_id='cluster-b'), connection, gateway=True)
    assert resolve_site_settings(settings, connection, gateway=False).site_read_base_url is None


def test_following_the_site_page_hint_keeps_the_selected_service(tmp_path):
    body = sample();body.update(has_more=True, next_cursor='site-a')
    def reply(call, count):
        if count == 1:
            return 200, body
        assert parse_qs(urlsplit(call['path']).query) == {'limit':['50'], 'cursor':['site-a']}
        return 200, {**body, 'items':[], 'count':0, 'has_more':False, 'next_cursor':None}
    with http_endpoint(reply) as (origin, calls):
        env = {'SAI_TOKEN':'test-user', 'XDG_CONFIG_HOME':str(tmp_path/'missing')}
        out, err = StringIO(), StringIO()
        assert main(['sites','--format','table','--base-url',origin],environ=env,stdout=out,stderr=err) == 0
        command = shlex.split(out.getvalue().split('Next: ')[1])[1:]
        assert main(command,environ=env,stdout=StringIO(),stderr=err) == 0, err.getvalue()
        assert len(calls) == 2
