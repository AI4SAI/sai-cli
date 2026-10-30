from copy import deepcopy
from io import StringIO
import json
import shlex
from pathlib import Path

import pytest

from sai_cli.cli import main
from sai_cli.errors import ContractError
from sai_cli.invitations import Invitations, render_invitations
from test_site_transport import http_endpoint


def sample(name="collaboration-invitation"):
    return json.loads((Path(__file__).resolve().parents[1]/"contracts"/name/"v2/sample.json").read_text())


@pytest.mark.parametrize("prefix", [False, True])
def test_real_http_recipient_list_accept_and_readback_without_site_or_native_tools(tmp_path, prefix, monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    detail = sample()
    def reply(call, count):
        assert call["bearer"] == "Bearer test-user" and call["capability"] is None
        if count == 1:
            assert call["path"] == "/v1/account/cli/invitations?limit=50"
            return 200, sample("collaboration-invitations")
        if call["method"] == "POST":
            assert call["path"] == "/v1/account/cli/invitations/invitation-example/accept"
            assert call["body"] == {"schema_version": "collaboration.invitation-accept/v2", "compute_enabled": False}
            detail["invitation"].update(status="accepted", accepted_at="2030-01-01T00:00:00Z")
            detail["next_action"] = "observe"
            detail["deliveries"] = [{"task_id":"task-example","generation":1,"site_id":"site-a",
                                      "status":"queued","finished_at":None,"workspace_available":False}]
        return 200, detail
    with http_endpoint(reply) as (origin, calls):
        env = {"SAI_TOKEN":"test-user","XDG_CONFIG_HOME":str(tmp_path/"config"),"PATH":"","SAI_REQUIRE_SITE_CAPABILITY":"1"}
        for command in [["invitations","list"],["invitations","show","invitation-example"],
                        ["invitations","accept","invitation-example"],
                        ["invitations","accept","invitation-example","--apply"],
                        ["invitations","show","invitation-example"]]:
            connection = ["--base-url",origin]
            output, error = StringIO(), StringIO()
            args = connection+command if prefix else command+connection
            assert main(args,environ=env,stdout=output,stderr=error) == 0,error.getvalue()
            assert not error.getvalue()
            result = json.loads(output.getvalue())
        assert [call["method"] for call in calls] == ["GET","GET","GET","GET","POST","GET"]
        assert result["invitation"]["status"] == "accepted" and result["deliveries"][0]["status"] == "queued"
        assert "等待执行" in render_invitations(Invitations(result))


@pytest.mark.parametrize("status", [401,403,409,503])
def test_accept_failure_is_not_retried_and_extra_scope_selectors_make_no_request(tmp_path,status,monkeypatch):
    monkeypatch.setenv("NO_PROXY","127.0.0.1,localhost")
    def reply(call, count):
        return ((200, sample()) if call["method"] == "GET" else
                (status, {"detail":{"code":"invitation_permissions_changed","token":"never-output"}}))
    with http_endpoint(reply) as (origin,calls):
        env={"SAI_TOKEN":"test-user","SAI_API_BASE_URL":origin,"XDG_CONFIG_HOME":str(tmp_path/"config")}
        for flags in [["--site","site-a"],["--cluster","cluster-a"]]:
            output,error=StringIO(),StringIO()
            assert main(["invitations","accept","invitation-example","--apply",*flags],environ=env,stdout=output,stderr=error)==2
            assert not output.getvalue() and not calls
        output,error=StringIO(),StringIO()
        assert main(["invitations","accept","invitation-example","--apply"],environ=env,stdout=output,stderr=error)!=0
        assert not output.getvalue() and [call["method"] for call in calls]==["GET","POST"]
        assert "never-output" not in error.getvalue()


def test_invitation_allowlist_binding_pagination_and_terminal_controls():
    value=sample()
    value["invitation"].update(invitation_token="never-output",directory_path="private-path",email="private@example.org")
    result=Invitations.detail(value,invitation_id="invitation-example",request_id="r")
    assert all(word not in json.dumps(result.as_dict()) for word in ["never-output","private-path","email"])
    with pytest.raises(ContractError): Invitations.detail(value,invitation_id="other",request_id="r")
    for target,bad in [("target_label","fake\nrow"),("site_label","unsafe\x1b[31m"),("role","owner"),
                       ("has_compute_resources",1),("compute_enabled",1)]:
        malformed=deepcopy(value);malformed["invitation"][target]=bad
        with pytest.raises(ContractError): Invitations.detail(malformed,invitation_id="invitation-example",request_id="r")
    page=sample("collaboration-invitations")
    with pytest.raises(ContractError): Invitations.page(page,limit=1,cursor="invitation-z",request_id="r")
    page.update(has_more=True,next_cursor="invitation-example")
    assert Invitations.page(page,limit=1,cursor=None,request_id="r").values["has_more"]
    page["next_cursor"]="wrong"
    with pytest.raises(ContractError): Invitations.page(page,limit=1,cursor=None,request_id="r")


@pytest.mark.parametrize("value", ["$(id)","x;id","-unexpected","a"*65,"bad\nvalue"])
def test_invitation_references_reject_shell_syntax_and_contract_overflow(value):
    page=sample("collaboration-invitations")
    page["items"][0]["invitation_id"]=value
    page.update(has_more=True,next_cursor=value)
    with pytest.raises(ContractError): Invitations.page(page,limit=1,cursor=None,request_id="r")
    detail=sample()
    detail["invitation"]["site_id"]=value
    with pytest.raises(ContractError): Invitations.detail(detail,invitation_id="invitation-example",request_id="r")


@pytest.mark.parametrize("site", ["default","GLOBAL"])
def test_invitation_sites_are_canonical(site):
    detail=sample();detail["invitation"]["site_id"]=site
    with pytest.raises(ContractError): Invitations.detail(detail,invitation_id="invitation-example",request_id="r")


@pytest.mark.parametrize('connection', ['profile', 'base-url'])
@pytest.mark.parametrize('prefix', [False, True])
def test_following_invitation_page_keeps_service_profile_and_page_size(tmp_path, connection, prefix):
    from urllib.parse import parse_qs, urlsplit
    page = sample('collaboration-invitations')
    page.update(has_more=True, next_cursor='invitation-example')
    def selected_reply(call, count):
        query = parse_qs(urlsplit(call['path']).query)
        assert query == {'limit': ['1'], **({'cursor': ['invitation-example']} if count > 1 else {})}
        return 200, page if count == 1 else {**page, 'items': [], 'count': 0, 'has_more': False, 'next_cursor': None}
    with http_endpoint(lambda *_: (200, page)) as (default, default_calls), http_endpoint(selected_reply) as (selected, calls):
        config = tmp_path / 'connection with spaces.toml'
        config.write_text(f'[profiles.default]\nbase_url={json.dumps(default)}\n'
                          f'[profiles.chosen]\nbase_url={json.dumps(selected)}\n')
        config.chmod(0o600)
        flags = ['--config', str(config), '--profile', 'chosen'] if connection == 'profile' else [
            '--config', str(config), '--base-url', selected]
        command = ['invitations', 'list', '--limit', '1', '--format', 'table']
        env = {'SAI_TOKEN': 'test-user', 'XDG_CACHE_HOME': str(tmp_path / 'cache')}
        output, error = StringIO(), StringIO()
        assert main([*flags, *command] if prefix else [*command, *flags],
                    environ=env, stdout=output, stderr=error) == 0, error.getvalue()
        following = shlex.split(output.getvalue().split('下一页：')[1])[1:]
        assert main(following, environ=env, stdout=StringIO(), stderr=error) == 0, error.getvalue()
        assert len(calls) == 2 and not default_calls


@pytest.mark.parametrize("failure", ["v1", "missing-compute"])
def test_incompatible_preflight_never_accepts(tmp_path, failure):
    detail = sample()
    del detail["invitation"]["compute_enabled"]
    if failure == "v1":
        detail["schema_version"] = "collaboration.invitation/v1"
    with http_endpoint(lambda *_: (200, detail)) as (origin, calls):
        output, error = StringIO(), StringIO()
        env = {"SAI_API_BASE_URL": origin, "SAI_TOKEN": "test-user", "XDG_CONFIG_HOME": str(tmp_path / "config")}
        assert main(["invitations", "accept", "invitation-example", "--apply"],
                    environ=env, stdout=output, stderr=error) == 7
        assert not output.getvalue() and [call["method"] for call in calls] == ["GET"]
        if failure == "v1":
            assert "Update the paired Portal and CLI" in error.getvalue()


def test_preview_requires_only_read_and_confirmation_keeps_selected_service(tmp_path):
    def reply(call, count):
        if call["method"] == "POST":
            return 403, {"detail": {"code": "identity_scope_insufficient"}}
        return 200, sample()
    with http_endpoint(reply) as (origin, calls):
        config = tmp_path / "chosen service.toml"
        config.write_text(f'[profiles.chosen]\nbase_url={json.dumps(origin)}\n')
        config.chmod(0o600)
        env = {"SAI_TOKEN": "read-only-user", "XDG_CONFIG_HOME": str(tmp_path / "config")}
        output, error = StringIO(), StringIO()
        assert main(["invitations", "accept", "invitation-example", "--format", "table",
                     "--config", str(config), "--profile", "chosen"],
                    environ=env, stdout=output, stderr=error) == 0, error.getvalue()
        assert [call["method"] for call in calls] == ["GET"]
        assert "编辑文件 · 不含计算权限" in output.getvalue()
        confirmation = shlex.split(output.getvalue().split("确认接受：")[1])[1:]
        assert "--apply" in confirmation
        assert main(confirmation, environ=env, stdout=StringIO(), stderr=error) == 4
        assert [call["method"] for call in calls] == ["GET", "GET", "POST"]


@pytest.mark.parametrize("action", ["complete_identity_assurance", "observe"])
def test_invitation_recovery_uses_selected_origin_and_reads_the_same_result(tmp_path, action):
    detail = sample()
    detail["next_action"] = action
    detail["invitation"]["status"] = "pending" if action == "complete_identity_assurance" else "accepted"
    detail["verification_url"] = "/portal/#/portal/account/identity-assurance" if action == "complete_identity_assurance" else None
    with http_endpoint(lambda *_: (200, detail)) as (origin, calls):
        config = tmp_path / "selected service.toml"
        config.write_text(f'[profiles.chosen]\nbase_url={json.dumps(origin)}\n')
        config.chmod(0o600)
        env = {"SAI_TOKEN": "read-only-user", "XDG_CONFIG_HOME": str(tmp_path / "config")}
        args = ["invitations", "show", "invitation-example", "--config", str(config), "--profile", "chosen"]
        output, error = StringIO(), StringIO()
        assert main(args, environ=env, stdout=output, stderr=error) == 0, error.getvalue()
        result = json.loads(output.getvalue())
        expected_url = origin + detail["verification_url"] if detail["verification_url"] else None
        assert result["verification_url"] == expected_url
        output = StringIO()
        assert main([*args, "--format", "table"], environ=env, stdout=output, stderr=error) == 0, error.getvalue()
        if expected_url:
            assert expected_url in output.getvalue()
        assert "auth login" not in output.getvalue()
        following = shlex.split(output.getvalue().split("查看进度：")[1].strip())[1:]
        assert main(following, environ=env, stdout=StringIO(), stderr=error) == 0, error.getvalue()
        assert [call["method"] for call in calls] == ["GET", "GET", "GET"]
        assert all(call["path"] == "/v1/account/cli/invitations/invitation-example" for call in calls)


@pytest.mark.parametrize("path", ["https://other.example.org/verify", "//other.example.org/verify", "/unexpected", "\x1b[31m"])
def test_invitation_recovery_cannot_redirect_to_another_location(path):
    detail = sample()
    detail.update(next_action="complete_identity_assurance", verification_url=path)
    with pytest.raises(ContractError):
        Invitations.detail(detail, invitation_id="invitation-example", request_id="r")


@pytest.mark.parametrize("kind, role, compute, project_budget, expected", [
    ("project", "read", False, False, "查看文件 · 不含计算权限"),
    ("project", "write", False, True, "编辑文件 · 不含计算权限"),
    ("project", "write", True, False, "编辑文件 · 使用项目账户计算 · 计算费用由所属组织承担"),
    ("project", "write", True, True, "编辑文件 · 使用项目账户计算 · 计算费用由所属组织承担，并受本项目预算限制"),
    ("project", "admin", False, True, "项目管理员 · 编辑文件 · 不含计算权限"),
    ("organization", "admin", True, False, "组织管理员 · 使用组织账户计算 · 计算费用由本组织承担"),
    ("directory", "write", False, False, "编辑文件 · 不含计算权限"),
])
def test_capability_and_payer_rendering_are_independent_of_governance_and_project_resources(
    kind, role, compute, project_budget, expected,
):
    detail = sample()
    detail["invitation"].update(target_kind=kind, role=role, compute_enabled=compute,
        uses_project_budget=project_budget, relationship_scope="directory" if kind == "directory" else "global",
        has_compute_resources=kind != "directory")
    result = Invitations.detail(detail, invitation_id="invitation-example", request_id="r")
    assert expected in render_invitations(result)
    page = sample("collaboration-invitations")
    page["items"] = [detail["invitation"]]
    assert expected in render_invitations(Invitations.page(page, limit=1, cursor=None, request_id="r"))
    if not compute:
        assert "计算费用由" not in render_invitations(result)
