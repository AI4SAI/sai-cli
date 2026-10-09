import json
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

from sai_cli.auth import TokenLease
from sai_cli.client import JobQuery, PortalClient
from sai_cli.errors import ConfigError, ContractError, ForbiddenError
from sai_cli.job_web_context import JobWebContext
from sai_cli.transport import JsonTransport
from test_site_transport import http_endpoint


def sample():
    return {"schema_version": "jobs.web-context/v1", "workspace_key": "project:project-example",
            "site_id": "site-a", "cluster_id": "cluster-a", "scope_type": "project_account",
            "slurm_account_id": "account-project", "job_id": "12345_0",
            "observed_at": "2026-09-23T01:00:00Z", "submit_time": "2026-07-31T00:00:00Z", "restart_count": 0}


def test_shared_web_context_sample_round_trips():
    payload = json.loads((Path(__file__).resolve().parents[1] / "contracts/job-web-context/v1/sample.json").read_text())
    assert JobWebContext.from_payload(payload, request_id="shared").as_dict() == payload


def test_web_context_allowlist_and_same_origin_url_preserve_old_observation():
    payload = sample()
    result = JobWebContext.from_payload({**payload, "url": "https://other.example", "token": "hidden"}, request_id="web")
    assert result.as_dict() == payload
    url = result.web_url("https://portal.example.org/api", observed_at="2026-09-23T00:00:00Z",
                         submit_time=None, restart_count=None)
    parsed = urlsplit(url)
    assert (parsed.scheme, parsed.netloc, parsed.path, parsed.query) == ("https", "portal.example.org", "/portal/", "")
    path, query = parsed.fragment.split("?", 1)
    assert path == "/portal/workspaces/project%3Aproject-example/site-a/jobs"
    assert json.loads(parse_qs(query)["job_context"][0]) == {
        "workspace_key": payload["workspace_key"], "site_id": "site-a", "cluster_id": "cluster-a", "job_id": "12345_0",
        "observed_at": "2026-09-23T00:00:00Z", "submit_time": None, "restart_count": None,
    }
    assert "hidden" not in url and "other.example" not in url
    assert not result.changed_since(submit_time="2026-07-31T00:00:00.000Z", restart_count=0)
    assert not result.changed_since(submit_time=None, restart_count=None)
    assert result.changed_since(submit_time="2026-07-30T00:00:00Z", restart_count=0)
    assert result.changed_since(submit_time=payload["submit_time"], restart_count=1)


@pytest.mark.parametrize("field,value", [
    ("workspace_key", "project:../../other"), ("workspace_key", "org:project-example"),
    ("scope_type", "self"), ("site_id", "site-a\n"), ("cluster_id", "other/site"),
    ("job_id", "12345_[0-9]"), ("job_id", True), ("job_id", "12345_0\n"),
    ("slurm_account_id", "invalid/owner"), ("slurm_account_id", "x" * 129),
    ("observed_at", "2026-02-30T00:00:00Z"), ("observed_at", "2026-09-23T00:00Z"),
    ("submit_time", "2026-09-23T00:00:00+08:00"), ("restart_count", True), ("restart_count", 65536),
])
def test_web_context_rejects_malformed_mapping(field, value):
    with pytest.raises(ContractError):
        JobWebContext.from_payload({**sample(), field: value}, request_id="web")


def test_web_context_requires_every_modeled_field_and_exact_request_binding():
    for field in sample():
        payload = sample()
        del payload[field]
        with pytest.raises(ContractError):
            JobWebContext.from_payload(payload, request_id="web")
    result = JobWebContext.from_payload(sample(), request_id="web")
    binding = dict(site_id="site-a", cluster_id="cluster-a", scope="project_account",
                   account_id="account-project", job_id="12345_0", request_id="web")
    result.require_request_binding(**binding)
    result.require_request_binding(**{**binding, "scope": "self", "account_id": None, "cluster_id": None})
    for changed in ({"site_id": "other"}, {"cluster_id": "other"}, {"scope": "org_account"},
                    {"account_id": "other"}, {"job_id": "12345"}, {"job_id": "12345_7"},
                    {"workspace_key": "project:other-owner"}):
        with pytest.raises(ContractError):
            result.require_request_binding(**{**binding, **changed})


def test_web_context_http_is_identity_only_and_keeps_exact_scope(tmp_path, monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    payload, failure = sample(), False
    def reply(call, _):
        if failure:
            return 403, {"detail": {"code": "job_navigation_workspace_denied", "message": "Workspace cannot be opened"}}
        return 200, payload
    def forbidden(*args, **kwargs):
        pytest.fail("navigation must not acquire a site capability or contact the site origin")
    with http_endpoint(reply) as (origin, calls):
        client = PortalClient(transport=JsonTransport(base_url=origin, timeout_seconds=2),
            token_provider=SimpleNamespace(get=lambda: TokenLease("identity-token", None, "environment")),
            capability_provider=SimpleNamespace(get=forbidden), site_transport=SimpleNamespace(request=forbidden))
        for query in (JobQuery(site_id="site-a"), JobQuery(site_id="site-a", cluster_id="cluster-a",
                      scope="project-account", account_id="account-project", partition="gpu", states=("R",), limit=2),
                      JobQuery(site_id="site-a", scope="project-account", account_name="legacy-project"),
                      JobQuery(site_id="site-a", scope="project-account", workspace_key="project:project-example")):
            assert client.job_web_context("12345_0", query).as_dict() == payload
        for invalid in ("12345_[0-9]", "12345/0", "123\n45", "12345+0"):
            with pytest.raises(ConfigError):
                client.job_web_context(invalid, JobQuery(site_id="site-a"))
        failure = True
        with pytest.raises(ForbiddenError) as error:
            client.job_web_context("12345_0", JobQuery(site_id="site-a"))
        assert error.value.code == "job_navigation_workspace_denied"
    assert len(calls) == 5
    assert all(c["method"] == "GET" and c["bearer"] == "Bearer identity-token" and c["capability"] is None for c in calls)
    parsed = [urlsplit(c["path"]) for c in calls]
    assert all(p.path == "/v1/slurm/cli/jobs/12345_0/web-context" for p in parsed)
    assert parse_qs(parsed[0].query) == {"site_id": ["site-a"], "scope_type": ["self"], "source_preference": ["live"]}
    assert parse_qs(parsed[1].query) == {"site_id": ["site-a"], "cluster_id": ["cluster-a"],
        "scope_type": ["project_account"], "slurm_account_id": ["account-project"], "source_preference": ["live"]}
    assert parse_qs(parsed[2].query)["slurm_account_name"] == ["legacy-project"]
    assert parse_qs(parsed[3].query) == {"site_id": ["site-a"], "scope_type": ["project_account"],
        "workspace_key": ["project:project-example"], "source_preference": ["live"]}


def test_org_job_navigation_keeps_source_scope_and_authorized_project_target():
    from copy import deepcopy
    from pathlib import Path
    payload=json.loads((Path(__file__).resolve().parents[1]/'contracts/job-web-context/v1/sample.json').read_text())
    payload.update(schema_version='jobs.web-context/v2',source_context={
        'scope_type':'org_account','slurm_account_id':'org-account','workspace_key':'org:example'})
    result=JobWebContext.from_payload(payload,request_id='navigation')
    result.require_request_binding(site_id=result.site_id,cluster_id=result.cluster_id,scope='org_account',
        account_id='org-account',workspace_key='org:example',job_id=result.job_id,request_id='navigation')
    assert result.as_dict()==payload
    with pytest.raises(ContractError):
        result.require_request_binding(site_id=result.site_id,cluster_id=result.cluster_id,scope='org_account',
            account_id='other',workspace_key='org:example',job_id=result.job_id,request_id='navigation')
