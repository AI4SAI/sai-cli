from copy import deepcopy
from io import StringIO
import os
import shlex
import json
from uuid import UUID

import pytest

from sai_cli.cli import main
from sai_cli.default_account import DefaultAccountState
from sai_cli.errors import ContractError
from test_site_transport import http_endpoint


def state():
    return {
        "schema_version": "account.defaults/v1", "scope": "user",
        "site_id": "site-a", "cluster_id": "cluster-a", "default_account_id": None,
        "effective_account_id": "account-personal",
        "choices": [{"id": "account-personal", "name": "personal-alice", "kind": "personal"},
                    {"id": "account-research", "name": "org-research", "kind": "org"}],
        "deliveries": [{"site_id": "site-a", "cluster_id": "cluster-a", "state": "applied",
                        "task_id": "projection-a", "generation": 1, "applied_at": "2026-10-09T00:00:00Z"}],
    }


def acceptance(call):
    return {"schema_version": "account.default-change/v1", "scope": "user", "state": "accepted",
            "request_id": call["idempotency_key"], "previous_account_id": call["body"]["expected_account_id"],
            "default_account_id": call["body"]["account_id"],
            "site_projections": [{"site_id": "site-a", "task_id": "projection-a", "generation": 2}]}


def invoke(tmp_path, origin, args, *, prefix=False):
    out, err = StringIO(), StringIO()
    connection = ["--base-url", origin]
    code = main(connection + args if prefix else args + connection,
                environ={"SAI_TOKEN": "identity-user-token", "XDG_CONFIG_HOME": str(tmp_path / "config"),
                         "XDG_DATA_HOME": str(tmp_path / "data"), "XDG_CACHE_HOME": str(tmp_path / "cache")},
                stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


@pytest.mark.parametrize("prefix", [False, True])
def test_real_http_read_and_explicit_global_write(tmp_path, monkeypatch, prefix):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    def respond(call, count):
        assert call["bearer"] == "Bearer identity-user-token" and call["capability"] is None
        if count == 1:
            assert call["method"] == "GET" and call["path"] == "/v1/account/cli/defaults?site_id=site-a"
            return 200, state()
        assert call["method"] == "PUT" and call["path"] == "/v1/account/cli/defaults"
        assert call["idempotency_key"] == "request-example-one"
        assert call["body"] == {"account_id": "account-research", "expected_account_id": None}
        return 200, acceptance(call)
    with http_endpoint(respond) as (origin, calls):
        code, output, error = invoke(tmp_path, origin, ["account", "defaults", "--site", "site-a"], prefix=prefix)
        assert code == 0 and json.loads(output) == state() and error == ""
        code, output, error = invoke(tmp_path, origin, ["account", "set-default", "account-research",
            "--if-current", "auto", "--request-id", "request-example-one"], prefix=prefix)
        assert code == 0 and not error
        assert json.loads(output)["state"] == "accepted"
        assert len(calls) == 2


@pytest.mark.parametrize('managed', [False, True])
def test_printed_default_account_readback_keeps_service_and_affected_site(tmp_path, monkeypatch, managed):
    def respond(call, count):
        if count == 1:
            assert call['method'] == 'PUT'
            return 200, acceptance(call)
        assert call['method'] == 'GET' and call['path'] == '/v1/account/cli/defaults?site_id=site-a'
        return 200, state()
    with http_endpoint(respond) as (origin, calls):
        from sai_cli import config as config_module
        config = tmp_path/'config.toml'
        config.write_text('[profiles.default]\n'+f'base_url={json.dumps(origin)}\nsite_id="site-a"\nrequire_site_capability=true\n')
        config.chmod(0o600)
        monkeypatch.setattr(config_module, '_MANAGED_CONFIG_PATH', config)
        monkeypatch.setattr(config_module, '_MANAGED_CONFIG_OWNER_UID', os.getuid())
        env = {'SAI_TOKEN':'identity-user-token','XDG_CONFIG_HOME':str(tmp_path/'missing')}
        if managed:
            env['SAI_MANAGED_LOGIN_NODE'] = '1'
        out, err = StringIO(), StringIO()
        options = [] if managed else ['--config',str(config)]
        assert main(['account','set-default','account-research','--if-current','auto',
                     '--request-id','request-example-one','--format','table',*options],
                    environ=env,stdout=out,stderr=err) == 0, err.getvalue()
        command = shlex.split(out.getvalue().split('结果：')[1])[1:]
        out, err = StringIO(), StringIO()
        assert main(command,environ=env,stdout=out,stderr=err) == 0, err.getvalue()
        assert "默认计算账户：自动选择（全局）" in out.getvalue() and len(calls) == 2
        assert "本站选择结果：personal-alice" in out.getvalue()


@pytest.mark.parametrize("saved, selected, target", [
    (None, "org-research", "account-research"),
    ("account-personal", "account-research", "account-research"),
    ("account-research", "auto", None),
])
def test_human_discovers_previews_and_executes_default_change_with_readback(tmp_path, monkeypatch, saved, selected, target):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    current = state()
    current["default_account_id"] = saved
    env = {"SAI_TOKEN": "identity-user-token", "XDG_CONFIG_HOME": str(tmp_path / "config"),
           "XDG_DATA_HOME": str(tmp_path / "data"), "XDG_CACHE_HOME": str(tmp_path / "cache")}

    def execute(argv):
        out, err = StringIO(), StringIO()
        assert main(argv, environ=env, stdout=out, stderr=err) == 0, err.getvalue()
        assert not err.getvalue()
        return out.getvalue()

    def respond(call, count):
        assert call["bearer"] == "Bearer identity-user-token" and call["capability"] is None
        if count == 3:
            assert call["method"] == "PUT" and call["path"] == "/v1/account/cli/defaults"
            assert call["body"] == {"account_id": target, "expected_account_id": saved}
            assert UUID(call["idempotency_key"]).version == 4
            current["default_account_id"] = target
            current["effective_account_id"] = target or "account-personal"
            current["deliveries"][0].update(generation=2, applied_at="2026-10-09T00:01:00Z")
            return 200, acceptance(call)
        assert call["method"] == "GET" and call["path"] == "/v1/account/cli/defaults?site_id=site-a"
        return 200, current

    with http_endpoint(respond) as (origin, calls):
        discovery = execute(["account", "defaults", "--site", "site-a", "--format", "table", "--base-url", origin])
        assert "本站可选：personal-alice, org-research" in discovery
        assert "account-research" not in discovery and "--request-id" not in discovery
        preview_argv = shlex.split(next(line.removeprefix("预览切换：") for line in discovery.splitlines()
                                       if line.startswith("预览切换：")))[1:]
        preview_argv[preview_argv.index("ACCOUNT_NAME")] = selected
        preview = execute(preview_argv)
        names = {row["id"]: row["name"] for row in current["choices"]}
        previous = names[saved] if saved else "自动选择"
        chosen = names[target] if target else "自动选择"
        assert f"切换全局默认：{previous} → {chosen}" in preview
        assert "本站可选：" not in preview
        assert len(calls) == 2 and all(call["method"] == "GET" for call in calls)
        apply_argv = shlex.split(next(line.removeprefix("确认切换：") for line in preview.splitlines()
                                     if line.startswith("确认切换：")))[1:]
        assert apply_argv[:3] == ["account", "set-default", target or "auto"]
        assert "--site" not in apply_argv
        accepted = execute(apply_argv)
        read_argv = shlex.split(next(line.removeprefix("查看站点结果：") for line in accepted.splitlines()
                                    if line.startswith("查看站点结果：")))[1:]
        readback = execute(read_argv)
        assert f"默认计算账户：{chosen}（全局）" in readback
        assert f"本站选择结果：{names[target or 'account-personal']}" in readback and "已收到应用回执" in readback
        assert len(calls) == 4


@pytest.mark.parametrize("ambiguous", [False, True])
def test_default_change_preview_rejects_unavailable_or_ambiguous_choice(tmp_path, monkeypatch, ambiguous):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    current = state()
    if ambiguous:
        current["choices"].append({"id": "account-other", "name": "org-research", "kind": "project"})
    with http_endpoint(lambda *_: (200, current)) as (origin, calls):
        code, output, error = invoke(tmp_path, origin, ["account", "defaults", "--site", "site-a",
            "--select", "org-research" if ambiguous else "unavailable-account", "--format", "table"])
        assert code == 2 and output == "" and len(calls) == 1
        assert calls[0]["method"] == "GET"
        assert ("名称不唯一" if ambiguous else "本站可选") in error


@pytest.mark.parametrize("status", [401, 403, 409, 503])
def test_failed_write_is_not_retried_or_printed_as_success(tmp_path, monkeypatch, status):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    with http_endpoint(lambda *_: (status, {"detail": {"code": "default_account_changed", "token": "private-secret"}})) as (origin, calls):
        code, out, err = invoke(tmp_path, origin, ["account", "set-default", "account-research", "--if-current", "auto",
                                                "--request-id", "request-example-one"])
    assert code != 0 and out == "" and len(calls) == 1
    assert "private-secret" not in err


def test_rejects_mismatched_acceptance_and_site_bound_global_write(tmp_path, monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    with http_endpoint(lambda call, _: (200, {**acceptance(call), "default_account_id": "wrong-account"})) as (origin, calls):
        args = ["account", "set-default", "account-research", "--if-current", "auto", "--request-id", "request-example-one"]
        code, out, err = invoke(tmp_path, origin, args)
        assert code == 7 and out == "" and len(calls) == 1
        code, out, err = invoke(tmp_path, origin, args + ["--site", "site-a"])
        assert code == 2 and out == "" and len(calls) == 1


def test_response_allowlist_and_receipt_consistency():
    value = state()
    value["private_path"] = "hidden-value"
    value["deliveries"][0]["raw_receipt"] = {"token": "hidden-value"}
    parsed = DefaultAccountState.from_payload(value, site_id="site-a", request_id="read")
    assert "hidden-value" not in json.dumps(parsed.as_dict())
    for field, bad in (("state", "pending"), ("applied_at", None), ("generation", True), ("task_id", None)):
        altered = deepcopy(value)
        altered["deliveries"][0][field] = bad
        with pytest.raises(ContractError):
            DefaultAccountState.from_payload(altered, site_id="site-a", request_id="read")
    value["choices"][0]["name"] = "unsafe\x1b[31m"
    with pytest.raises(ContractError):
        DefaultAccountState.from_payload(value, site_id="site-a", request_id="read")
