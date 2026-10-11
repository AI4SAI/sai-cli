from copy import deepcopy
from io import StringIO
import json
from pathlib import Path

import pytest

from sai_cli.cli import main
from sai_cli.errors import ContractError
from sai_cli.invitations import Invitations, render_invitations
from test_site_transport import http_endpoint


def sample(name="collaboration-invitation"):
    return json.loads((Path(__file__).resolve().parents[1]/"contracts"/name/"v1/sample.json").read_text())


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
            assert call["body"] == {}
            detail["invitation"].update(status="accepted", accepted_at="2030-01-01T00:00:00Z")
            detail["next_action"] = "observe"
            detail["deliveries"] = [{"task_id":"task-example","generation":1,"site_id":"site-a",
                                      "status":"queued","finished_at":None,"workspace_available":False}]
        return 200, detail
    with http_endpoint(reply) as (origin, calls):
        env = {"SAI_TOKEN":"test-user","XDG_CONFIG_HOME":str(tmp_path/"config"),"PATH":"","SAI_REQUIRE_SITE_CAPABILITY":"1"}
        for command in [["invitations","list"],["invitations","show","invitation-example"],
                        ["invitations","accept","invitation-example"],["invitations","show","invitation-example"]]:
            connection = ["--base-url",origin]
            output, error = StringIO(), StringIO()
            args = connection+command if prefix else command+connection
            assert main(args,environ=env,stdout=output,stderr=error) == 0,error.getvalue()
            assert not error.getvalue()
            result = json.loads(output.getvalue())
        assert [call["method"] for call in calls] == ["GET","GET","POST","GET"]
        assert result["invitation"]["status"] == "accepted" and result["deliveries"][0]["status"] == "queued"
        assert "等待执行" in render_invitations(Invitations(result))


@pytest.mark.parametrize("status", [401,403,409,503])
def test_accept_failure_is_not_retried_and_extra_scope_selectors_make_no_request(tmp_path,status,monkeypatch):
    monkeypatch.setenv("NO_PROXY","127.0.0.1,localhost")
    with http_endpoint(lambda *_:(status,{"detail":{"code":"invitation_not_accepting","token":"never-output"}})) as (origin,calls):
        env={"SAI_TOKEN":"test-user","SAI_API_BASE_URL":origin,"XDG_CONFIG_HOME":str(tmp_path/"config")}
        for flags in [["--site","site-a"],["--cluster","cluster-a"]]:
            output,error=StringIO(),StringIO()
            assert main(["invitations","accept","invitation-example",*flags],environ=env,stdout=output,stderr=error)==2
            assert not output.getvalue() and not calls
        output,error=StringIO(),StringIO()
        assert main(["invitations","accept","invitation-example"],environ=env,stdout=output,stderr=error)!=0
        assert not output.getvalue() and len(calls)==1 and "never-output" not in error.getvalue()


def test_invitation_allowlist_binding_pagination_and_terminal_controls():
    value=sample()
    value["invitation"].update(invitation_token="never-output",directory_path="private-path",email="private@example.org")
    result=Invitations.detail(value,invitation_id="invitation-example",request_id="r")
    assert all(word not in json.dumps(result.as_dict()) for word in ["never-output","private-path","email"])
    with pytest.raises(ContractError): Invitations.detail(value,invitation_id="other",request_id="r")
    for target,bad in [("target_label","fake\nrow"),("site_label","unsafe\x1b[31m"),("role","owner"),("has_compute_resources",1)]:
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
