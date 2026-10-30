from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
import shlex

import pytest

from sai_cli.cli import main
from sai_cli.cli import build_parser
from sai_cli.errors import ContractError
from sai_cli.project_compute import ProjectCompute, render_project_compute
from test_site_transport import http_endpoint


def sample(kind):
    return json.loads((Path(__file__).resolve().parents[1]/"contracts"/kind/"v1/sample.json").read_text())


@pytest.mark.parametrize("prefix", [False, True])
def test_project_compute_preview_apply_and_late_replay_keep_one_intent(tmp_path, prefix):
    accepted = sample("project-compute-enable")
    writes = []
    def reply(call, _):
        if call["path"].startswith("/v1/account/cli/project-compute/requests/"):
            return (200, accepted) if writes else (404, {"detail":{"code":"project_compute_request_not_found"}})
        if call["method"] == "POST":
            assert call["body"] == {"site_id":"site-a", "expected":{k:sample("project-member")["member"][k]
                for k in ("role","compute_enabled","valid_from","expires_at")}}
            assert call["idempotency_key"] == "request-example"
            writes.append(call)
            return 200, accepted
        assert not writes, "late replay must recover acceptance without re-reading changed membership"
        return 200, sample("project-member")
    with http_endpoint(reply) as (origin, calls):
        config = tmp_path/"service with spaces.toml"
        config.write_text(f'[profiles.chosen]\nbase_url={json.dumps(origin)}\n')
        config.chmod(0o600)
        flags=["--config",str(config),"--profile","chosen"]
        command=["projects","enable-compute","project-example","member-example","--site","site-a","--request-id","request-example","--format","table"]
        output,error=StringIO(),StringIO()
        assert main(flags+command if prefix else command+flags,environ={"SAI_TOKEN":"test-user"},stdout=output,stderr=error)==0,error.getvalue()
        assert [c["method"] for c in calls]==["GET"]
        assert "Research team" in output.getvalue() and "受项目预算限制" in output.getvalue()
        apply=shlex.split(output.getvalue().split("确认启用：")[1].strip())[1:]
        for _ in range(2):
            out=StringIO()
            assert main(apply,environ={"SAI_TOKEN":"test-user"},stdout=out,stderr=error)==0,error.getvalue()
            assert "请求已受理" in out.getvalue()
            follow=shlex.split(out.getvalue().split("查看进度：")[1].strip())
            assert follow[:4]==["sai","projects","task","task-example"]
        assert len(writes)==1
        assert all(call["capability"] is None and call["bearer"]=="Bearer test-user" for call in calls)


def test_project_query_pagination_preserves_service_and_filter(tmp_path):
    page=sample("collaboration-projects");page.update(has_more=True,next_cursor="project-example")
    def reply(call,count):
        from urllib.parse import parse_qs,urlsplit
        q=parse_qs(urlsplit(call["path"]).query)
        assert q=={"limit":["1"],"q":["Research"],**({"cursor":["project-example"]} if count>1 else {})}
        return 200,page if count==1 else {**page,"items":[],"has_more":False,"next_cursor":None}
    with http_endpoint(reply) as (origin,calls):
        out,error=StringIO(),StringIO()
        env={"SAI_TOKEN":"test-user","XDG_CONFIG_HOME":str(tmp_path/"config")}
        assert main(["projects","list","--query","Research","--limit","1","--format","table","--base-url",origin],environ=env,stdout=out,stderr=error)==0,error.getvalue()
        following=shlex.split(out.getvalue().split("下一页：")[1].strip())[1:]
        assert main(following,environ=env,stdout=StringIO(),stderr=error)==0,error.getvalue()
        assert len(calls)==2


@pytest.mark.parametrize("failure", ["unavailable", "invalid_response", "state_changed", "member_pending", "idempotency_conflict"])
def test_apply_requires_request_key_and_does_not_retry_a_failed_write(tmp_path, failure):
    def reply(call,_):
        if "/requests/" in call["path"]:
            return 404,{"detail":{"code":"project_compute_request_not_found"}}
        if call["method"]=="POST":
            if failure == "state_changed":
                return 409,{"detail":{"code":"workspace_collaboration_changed"}}
            if failure == "member_pending":
                return 409,{"detail":{"code":"workspace_membership_change_pending"}}
            if failure == "idempotency_conflict":
                return 409,{"detail":{"code":"idempotency_conflict"}}
            return (503,{"detail":{"code":"temporarily_unavailable","raw":"never-print"}}) if failure == "unavailable" else (200,{})
        return 200,sample("project-member")
    with http_endpoint(reply) as (origin,calls):
        env={"SAI_TOKEN":"test-user","SAI_API_BASE_URL":origin,"XDG_CONFIG_HOME":str(tmp_path/"config")}
        args=["projects","enable-compute","project-example","member-example","--site","site-a","--apply"]
        out,error=StringIO(),StringIO()
        assert main(args,environ=env,stdout=out,stderr=error)==2 and not calls
        error=StringIO()
        code = {"invalid_response":7,"unavailable":6,"state_changed":2,"member_pending":2,"idempotency_conflict":2}[failure]
        assert main([*args,"--request-id","request-example"],environ=env,stdout=out,stderr=error)==code
        assert len([c for c in calls if c["method"]=="POST"])==1 and "never-print" not in error.getvalue()
        recovery = json.loads(error.getvalue())["error"]["recovery"]["argv"]
        assert recovery[:4] == (["sai","projects","member","project-example"] if failure in {"state_changed","member_pending"} else ["sai","projects","request","request-example"])


def test_member_scope_and_control_fields_are_allowlisted():
    good=sample("project-member")
    for field,value in [("membership_id","other"),("username","bad\nline"),("compute_enabled",1)]:
        bad=deepcopy(good);bad["member"][field]=value
        with pytest.raises(ContractError):
            ProjectCompute.parse(bad,schema="project.member/v1",request_id="r",project_id="project-example",membership_id="member-example",site_id="site-a")
    good["raw"]= "never-print";good["project"]["wallet_id"]="private"
    result=ProjectCompute.parse(good,schema="project.member/v1",request_id="r",project_id="project-example",membership_id="member-example",site_id="site-a").as_dict()
    assert "raw" not in result and "wallet_id" not in result["project"]


def test_followup_display_preserves_state_without_terminal_controls():
    payload = sample("project-member")
    payload["member"].update(compute_enabled=True, membership_status="expired")
    payload.update(enable_compute_allowed=False, unavailable_reason="member_not_current")
    payload["sites"][0].update(status="processing", task_id="task-example")
    args = build_parser().parse_args(["projects", "member", "project-example", "member-example", "--site", "site-a",
                                     "--config", "config\nwith\x85controls.toml"])
    rendered = render_project_compute(ProjectCompute(payload), args=args)
    assert "正在生效" in rendered and "查看进度" in rendered and "所有关联站点" in rendered
    assert "\x85" not in rendered and "\\x85" in rendered
    page = sample("project-members");page["items"][0] = payload["member"]
    assert "已过期" in render_project_compute(ProjectCompute(page), args=args)
