from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
import shlex

import pytest

from sai_cli.cli import build_parser, main
from sai_cli.discovery import authorization_scopes, describe
from sai_cli.errors import ContractError
from sai_cli.project_invitation import ProjectInvitation
from test_site_transport import http_endpoint


def sample(name):
    return json.loads((Path(__file__).resolve().parents[1] / "contracts/project-invitation/v1" / (name + ".json")).read_text())


def invite_args():
    return ["projects", "invite", "project-example", "--username", "researcher", "--role", "write",
            "--compute", "enabled", "--member-expires-at", "2027-06-30T18:00:00.123+08:00",
            "--site", "site-a"]


def test_invitation_preview_confirmation_uncertain_result_and_same_request_readback(tmp_path):
    preview, created, detail = sample("preview"), sample("created"), sample("detail")
    preview["terms"].update(membership_valid_from=None, membership_expires_at="2027-06-30T10:00:00Z",
                            ttl_hours=72, role="write", compute_enabled=True)
    saved, writes = {}, []

    def reply(call, _):
        if call["path"].endswith("/preview"):
            assert call["method"] == "POST"
            assert call["body"] == {"schema_version": "project.invitation-preview/v1",
                "site_id": "site-a", "invitee_username": "researcher", **preview["terms"]}
            return 200, preview
        if call["method"] == "POST":
            assert call["body"] == {"schema_version": "project.invitation-create/v1",
                "site_id": "site-a", "invitee_username": "researcher",
                "invitee_user_id": preview["invitee"]["user_id"], **preview["terms"]}
            key = call["idempotency_key"]
            writes.append(call)
            if key not in saved:
                saved[key] = {**created, "request_id": key}
                return 503, {"detail": {"code": "response_lost", "raw": "never-print"}}
            return 200, saved[key]
        if "/project-invitation-requests/" in call["path"]:
            return 200, saved[call["path"].rsplit("/", 1)[-1]]
        assert call["path"].endswith("/project-invitations/" + created["invitation_id"])
        return 200, detail

    with http_endpoint(reply) as (origin, calls):
        config = tmp_path / "service with spaces.toml"
        config.write_text(f'[profiles.chosen]\nbase_url={json.dumps(origin)}\n')
        config.chmod(0o600)
        env = {"SAI_TOKEN": "test-inviter", "XDG_CACHE_HOME": str(tmp_path / "cache")}
        flags = ["--config", str(config), "--profile", "chosen", "--format", "table"]
        out, err = StringIO(), StringIO()
        assert main(invite_args() + flags, environ=env, stdout=out, stderr=err) == 0, err.getvalue()
        assert len(calls) == 1 and not writes
        confirmation = next(line for line in out.getvalue().splitlines() if "sai projects invite " in line)
        command = shlex.split(confirmation[confirmation.index("sai projects invite "):])[1:]
        assert command[command.index("--invitee-id") + 1] == preview["invitee"]["user_id"]
        assert "--apply" in command and "--request-id" in command and "--format" in command
        out, err = StringIO(), StringIO()
        assert main(command, environ=env, stdout=out, stderr=err) == 6
        assert not out.getvalue() and "never-print" not in err.getvalue()
        recovery = err.getvalue().split("`", 2)[1]
        assert "projects invite-request" in recovery and "--format table" in recovery
        out, err = StringIO(), StringIO()
        assert main(shlex.split(recovery)[1:], environ=env, stdout=out, stderr=err) == 0, err.getvalue()
        assert len(writes) == 1
        follow = next(line for line in out.getvalue().splitlines() if "sai projects invitation " in line)
        command_read = shlex.split(follow[follow.index("sai projects invitation "):])[1:]
        assert "--site" not in command_read
        detail["invitation"].update(status="pending", accepted_at=None)
        detail["deliveries"] = []
        out = StringIO()
        assert main(command_read, environ=env, stdout=out, stderr=err) == 0, err.getvalue()
        assert "接受" in out.getvalue()
        detail["invitation"].update(status="accepted", accepted_at="2026-11-18T00:00:00Z")
        detail["deliveries"] = [{"task_id": "task-example", "site_id": "site-a", "generation": 1,
            "status": "running", "finished_at": None, "workspace_available": False}]
        out = StringIO()
        assert main(command_read, environ=env, stdout=out, stderr=err) == 0, err.getvalue()
        assert "接受" in out.getvalue() and "已加入" not in out.getvalue()
        detail["deliveries"][0].update(status="ready", finished_at="2026-11-18T00:01:00Z", workspace_available=True)
        assert main(command_read, environ=env, stdout=StringIO(), stderr=err) == 0, err.getvalue()
        assert main(command, environ=env, stdout=StringIO(), stderr=err) == 0, err.getvalue()
        assert len(saved) == 1 and writes[0] == writes[1]
        assert all(call["bearer"] == "Bearer test-inviter" and call["capability"] is None for call in calls)


@pytest.mark.parametrize("status,code,reason", [(401, 3, "invitation_rejected"), (403, 4, "invitation_rejected"),
    (409, 2, "invitation_rejected"), (503, 6, "invitation_rejected"), (409, 2, "idempotency_conflict")])
def test_invitation_denial_never_retries_write_or_changes_identity(tmp_path, status, code, reason):
    with http_endpoint(lambda *_: (status, {"detail": {"code": reason}})) as (origin, calls):
        args = invite_args() + ["--apply", "--invitee-id", "user-example", "--request-id", "request-example",
                                "--base-url", origin]
        out, err = StringIO(), StringIO()
        assert main(args, environ={"SAI_TOKEN": "test-inviter", "XDG_CONFIG_HOME": str(tmp_path)},
                    stdout=out, stderr=err) == code
        assert len(calls) == 1 and not out.getvalue()
        body = json.loads(err.getvalue())["error"]
        assert ("recovery" in body) == (status == 503 or reason == "idempotency_conflict")


def test_invitation_local_validation_and_global_readback_do_not_call_network(tmp_path):
    with http_endpoint(lambda *_: pytest.fail("invalid input reached the API")) as (origin, calls):
        env = {"SAI_TOKEN": "test-inviter", "SAI_API_BASE_URL": origin, "XDG_CONFIG_HOME": str(tmp_path)}
        bad_date = invite_args()
        bad_date[bad_date.index("--member-expires-at") + 1] = "2027-06-30T18:00:00"
        for command in (invite_args() + ["--apply"], bad_date,
                        ["projects", "invitation", "invite-example", "--site", "site-a"],
                        ["projects", "invite-request", "request-example", "--cluster", "cluster-a"]):
            assert main(command, environ=env, stdout=StringIO(), stderr=StringIO()) == 2
        assert calls == []


@pytest.mark.parametrize("identifier", ["invitation-example", "unsafe\ninvitation", {"raw": "private"}])
def test_pending_invitation_conflict_has_a_bounded_existing_object_recovery(tmp_path, identifier):
    with http_endpoint(lambda *_: (409, {"detail": {"code": "workspace_invitation_already_pending",
                                                  "invitation_id": identifier}})) as (origin, calls):
        error = StringIO()
        result = main(invite_args(), environ={"SAI_TOKEN": "test-inviter", "SAI_API_BASE_URL": origin,
                      "XDG_CONFIG_HOME": str(tmp_path)}, stdout=StringIO(), stderr=error)
        assert result == 2 and len(calls) == 1
        value = json.loads(error.getvalue())["error"]
        if identifier == "invitation-example":
            assert value["recovery"]["argv"][:4] == ["sai", "projects", "invitation", identifier]
        else:
            assert "recovery" not in value and "private" not in error.getvalue()


def test_existing_member_uses_the_current_member_reader(tmp_path):
    with http_endpoint(lambda *_: (409, {"detail": {"code": "project_invitation_member_exists"}})) as (origin, calls):
        error = StringIO()
        result = main(invite_args(), environ={"SAI_TOKEN": "test-inviter", "SAI_API_BASE_URL": origin,
                      "XDG_CONFIG_HOME": str(tmp_path)}, stdout=StringIO(), stderr=error)
        assert result == 2 and len(calls) == 1
        assert json.loads(error.getvalue())["error"]["recovery"]["argv"][:8] == [
            "sai", "projects", "members", "project-example", "--username", "researcher", "--site", "site-a"]


def test_invitation_scopes_are_discoverable_without_granting_them():
    parser = build_parser()
    result = describe(parser, ["projects", "invite"])["operations"][0]
    assert result["effect"] == "read" and result["site_required"]
    assert result["conditional_requirements"][0]["effect"] == "business_write"
    assert authorization_scopes(parser, ["projects", "invite"]) == (
        "sai.collaboration.invitations.write", "sai.collaboration.members.read")
    assert authorization_scopes(parser, ["projects", "invitation"]) == ("sai.collaboration.members.read",)
    assert authorization_scopes(parser, ["invitations", "accept"]) == (
        "sai.collaboration.invitations.accept", "sai.collaboration.invitations.read")


@pytest.mark.parametrize("field,value", [("project_id", "other-project"), ("invitee_id", "other-user"),
                                       ("username", "other-name"), ("key", "different-request")])
def test_created_invitation_must_match_the_confirmed_target_and_request(field, value):
    data = sample("created")
    bindings = {"project_id": data["project_id"], "invitee_id": data["invitee"]["user_id"],
                "username": data["invitee"]["username"], "key": data["request_id"]}
    bindings[field] = value
    with pytest.raises(ContractError):
        ProjectInvitation.parse(data, schema="project.invitation-create/v1", request_id="r", **bindings)


def test_preview_keeps_the_requested_terms_and_redacts_unknown_fields():
    data = sample("preview")
    data["raw"] = "never-print"
    data["invitee"]["email"] = "private@example.invalid"
    parsed = ProjectInvitation.parse(data, schema="project.invitation-preview/v1", request_id="r",
                                     terms=data["terms"])
    assert "raw" not in parsed.as_dict() and "email" not in parsed.as_dict()["invitee"]
    changed = deepcopy(data["terms"])
    changed["compute_enabled"] = not changed["compute_enabled"]
    with pytest.raises(ContractError):
        ProjectInvitation.parse(data, schema="project.invitation-preview/v1", request_id="r", terms=changed)


@pytest.mark.parametrize("mutation", ["invitation", "site", "kind", "label"])
def test_inviter_detail_binds_scope_and_rejects_terminal_controls(mutation):
    data = sample("detail")
    invitation_id, site = data["invitation"]["invitation_id"], data["invitation"]["site_id"]
    if mutation == "invitation":
        data["invitation"]["invitation_id"] = "another-invitation"
    elif mutation == "site":
        data["invitation"]["site_id"] = "site-b"
    elif mutation == "kind":
        data["invitation"].update(target_kind="directory", relationship_scope="directory")
    else:
        data["project"]["organization_label"] = "unsafe\x1b[2J"
    with pytest.raises(ContractError):
        ProjectInvitation.parse(data, schema="project.invitation/v1", request_id="r",
            invitation_id=invitation_id, site_id=site)
