from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import StringIO
import json
from pathlib import Path
import threading
import time

import pytest

from sai_cli.cli import main


@contextmanager
def http_endpoint(respond):
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def handle_call(self):
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length)) if length else None
            call = {"method": self.command, "path": self.path, "body": body,
                    "bearer": self.headers.get("Authorization"),
                    "capability": self.headers.get("X-SAI-Capability")}
            if self.headers.get("Idempotency-Key") is not None:
                call["idempotency_key"] = self.headers["Idempotency-Key"]
            calls.append(call)
            status, payload = respond(call, len(calls))
            encoded = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        do_GET = handle_call
        do_POST = handle_call
        do_PUT = handle_call

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", calls
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def issuer(call, count):
    assert call["method"] == "POST" and call["path"] == "/v1/authz/site-read"
    assert call["bearer"] == "Bearer identity-session-token" and call["capability"] is None
    body = call["body"]
    return 200, {
        "schema_version": "sai-site-read-capability/v1", "audience": "sai-site-read",
        "surface": "site-read", "site_id": body["site_id"], "cluster_id": body["cluster_id"],
        "operation": body["operation"], "expires_at": int(time.time()) + 120,
        "capability": f"opaque-capability-{count}",
    }


def profile(tmp_path, portal, gateway):
    config = tmp_path / "config.toml"
    config.write_text(
        '[profiles.default]\nsite_id="site-a"\ncluster_id="cluster-a"\n'
        'require_site_capability=true\n'
        f'base_url={json.dumps(portal)}\nsite_read_base_url={json.dumps(gateway)}\n'
    )
    config.chmod(0o600)
    return config


def invoke(config, tmp_path, command):
    stdout, stderr = StringIO(), StringIO()
    result = main(["--config", str(config), *command], environ={
        "SAI_TOKEN": "identity-session-token", "XDG_CACHE_HOME": str(tmp_path / "cache"),
    }, stdout=stdout, stderr=stderr)
    return result, stdout.getvalue(), stderr.getvalue()


@pytest.fixture
def site_payload(job_payload):
    return {
        "schema_version": "jobs/v1", "site_id": "site-a", "cluster_id": "cluster-a",
        "scope_type": "self", "subject": {"slurm_user": "alice", "slurm_account": None},
        "items": deepcopy(job_payload["items"]), "etag": "a" * 64, "has_more": False,
        "freshness": {"source": "squeue", "observed_at": "2026-09-22T00:00:00Z",
                      "ttl_seconds": 1, "age_seconds": 0, "stale": False},
    }


def test_two_origins_keep_identity_at_portal_and_exact_grant_at_gateway(tmp_path, site_payload):
    def gateway_reply(call, count):
        assert call["bearer"] is None
        assert call["capability"] == f"opaque-capability-{count}"
        result = deepcopy(site_payload)
        if call["path"].endswith("/12345"):
            result["freshness"]["source"] = "scontrol"
        return 200, result

    with http_endpoint(issuer) as (portal, issued), http_endpoint(gateway_reply) as (gateway, reads):
        config = profile(tmp_path, portal, gateway)
        result, output, errors = invoke(config, tmp_path, ["jobs", "list", "--partition", "gpu-standard", "--states", "R", "--limit", "2"])
        assert result == 0, errors
        assert json.loads(output) == site_payload
        result, output, errors = invoke(config, tmp_path, ["jobs", "show", "12345", "--format", "table"])
        assert result == 0, errors
        assert "scontrol" in output and "12345" in output
    assert [r["path"] for r in reads] == ["/v1/site-read/jobs", "/v1/site-read/jobs/12345"]
    assert issued[0]["body"]["partition"] == "gpu-standard"
    assert issued[0]["body"]["states"] == ["R"] and issued[0]["body"]["limit"] == 2
    assert issued[1]["body"]["operation"] == "jobs.detail" and issued[1]["body"]["job_id"] == "12345"


def test_workspace_switch_keeps_identity_at_portal_and_separates_capability_cache(tmp_path, site_payload):
    def gateway_reply(call, _):
        assert call["bearer"] is None
        suffix = "a" if call["capability"] == "opaque-capability-1" else "b"
        payload = deepcopy(site_payload)
        payload.update(scope_type="org_account", subject={"slurm_user": None, "slurm_account": "native-" + suffix})
        payload["items"][0]["slurm_account"] = "native-" + suffix
        return 200, payload

    with http_endpoint(issuer) as (portal, issued), http_endpoint(gateway_reply) as (gateway, reads):
        config = profile(tmp_path, portal, gateway)
        for owner in ("owner-a", "owner-b", "owner-a"):
            result, output, errors = invoke(config, tmp_path, ["jobs", "list", "--workspace-key", "org:" + owner])
            assert result == 0, errors
            assert json.loads(output)["subject"]["slurm_account"] == "native-" + owner[-1]
    assert [call["body"]["workspace_key"] for call in issued] == ["org:owner-a", "org:owner-b"]
    assert all(call["body"]["slurm_account_id"] is None and call["body"]["slurm_account_name"] is None for call in issued)
    assert [call["capability"] for call in reads] == ["opaque-capability-1", "opaque-capability-2", "opaque-capability-1"]


@pytest.mark.parametrize("status", [401, 403, 503])
@pytest.mark.parametrize("command", [["jobs", "list"], ["jobs", "allocation", "12345"]])
def test_fresh_capability_failure_does_not_retry_or_fall_back(tmp_path, site_payload, status, command):
    with http_endpoint(issuer) as (portal, issued), http_endpoint(lambda *_: (status, {"detail": "unavailable"})) as (gateway, reads):
        config = profile(tmp_path, portal, gateway)
        result, output, errors = invoke(config, tmp_path, command)
        assert result != 0 and output == "" and json.loads(errors)["error"]
    assert len(reads) == len(issued) == 1
    assert reads[0]["bearer"] is None


@pytest.mark.parametrize("renewed_status", [200, 401])
@pytest.mark.parametrize("allocation", [False, True])
def test_cached_capability_renews_once_without_sending_or_refreshing_bearer(
    tmp_path, site_payload, site_allocation_payload, renewed_status, allocation,
):
    payload = site_allocation_payload if allocation else site_payload
    command = ["jobs", "allocation", "12345"] if allocation else ["jobs", "list"]
    def gateway_reply(call, count):
        status = 200 if count == 1 else 401 if count == 2 else renewed_status
        return status, payload if status == 200 else {"detail": "expired"}

    with http_endpoint(issuer) as (portal, issued), http_endpoint(gateway_reply) as (gateway, reads):
        config = profile(tmp_path, portal, gateway)
        assert invoke(config, tmp_path, command)[0] == 0
        result, output, _ = invoke(config, tmp_path, command)
        assert (result == 0) == (renewed_status == 200)
        if renewed_status == 401:
            assert output == ""
    assert len(issued) == 2 and len(reads) == 3
    assert [c["capability"] for c in reads] == ["opaque-capability-1", "opaque-capability-1", "opaque-capability-2"]
    assert all(c["bearer"] is None for c in reads)


def test_allocation_uses_exact_operation_and_gateway_path(tmp_path, site_allocation_payload):
    site_allocation_payload["job"]["array_task_id"] = "7"
    with http_endpoint(issuer) as (portal, issued), http_endpoint(
        lambda *_: (200, site_allocation_payload),
    ) as (gateway, reads):
        config = profile(tmp_path, portal, gateway)
        for options in (["--site", "site-a", "jobs", "allocation", "12345_7"],
                        ["jobs", "allocation", "12345_7", "--site", "site-a", "--format", "table"]):
            result, output, errors = invoke(config, tmp_path, options)
            assert result == 0, errors
            if options[-1] == "table":
                assert "Array task: 7" in output and "compute-a" in output
            else:
                assert json.loads(output) == site_allocation_payload
        site_allocation_payload["job"]["array_task_id"] = None
        result, output, errors = invoke(config, tmp_path, ["jobs", "allocation", "12345_7"])
        assert result == 7 and output == ""
    assert len(issued) == 1
    assert issued[0]["body"] == {
        "operation": "jobs.allocation", "site_id": "site-a", "cluster_id": "cluster-a",
        "scope_type": "self", "slurm_account_id": None, "slurm_account_name": None,
        "partition": None, "states": [], "job_id": "12345_7", "limit": None,
    }
    assert all(c["path"] == "/v1/site-read/jobs/12345_7/allocation" and c["bearer"] is None for c in reads)


def test_optional_interconnect_uses_same_exact_capability_and_fails_if_absent(tmp_path, site_allocation_payload):
    nodes = site_allocation_payload['allocation']['nodes']
    site_allocation_payload['interconnect']={'schema_version':'node-interconnect-join/v1','nodes':[
        {'node':row['name'],'status':'unavailable','reason':'not_recorded'} for row in nodes]}
    with http_endpoint(issuer) as (portal,issued), http_endpoint(lambda *_:(200,site_allocation_payload)) as (gateway,reads):
        config=profile(tmp_path,portal,gateway)
        code,text,error=invoke(config,tmp_path,['jobs','allocation','12345','--with-interconnect'])
        assert code==0,error
        assert json.loads(text)['interconnect']==site_allocation_payload['interconnect']
        assert reads[0]['path']=='/v1/site-read/jobs/12345/allocation?include_interconnect=true'
        assert issued[0]['body']['operation']=='jobs.allocation' and reads[0]['bearer'] is None
        del site_allocation_payload['interconnect']
        assert invoke(config,tmp_path,['jobs','allocation','12345','--with-interconnect'])[0]==7


@pytest.mark.parametrize("capability", [False, True])
@pytest.mark.parametrize("command", ["allocation", "placement"])
def test_native_detail_requires_capability_and_an_available_site_endpoint(tmp_path, capability, command):
    connection = {"schema_version": "site.connection/v1", "site_id": "site-a", "cluster_id": "cluster-a",
                  "site_read_base_url": None}
    with http_endpoint(lambda *_: (200, connection)) as (portal, calls):
        config = tmp_path / "config.toml"
        config.write_text('[profiles.default]\nsite_id="site-a"\ncluster_id="cluster-a"\n'
                          f'base_url={json.dumps(portal)}\nrequire_site_capability={str(capability).lower()}\n')
        config.chmod(0o600)
        result, output, errors = invoke(config, tmp_path, ["jobs", command, "12345"])
    assert result == (6 if capability else 2) and output == ""
    assert [call["path"] for call in calls] == (["/v1/account/cli/sites/site-a/connection"] if capability else [])


@pytest.mark.parametrize('cluster_selection', [None, 'before', 'after', 'environment'])
@pytest.mark.parametrize('command', [['jobs', 'allocation', '12345'], ['jobs', 'list'], ['jobs', 'show', '12345']])
def test_portable_job_reads_resolve_the_selected_site_without_rewriting_profile(tmp_path, site_allocation_payload, site_payload, command, cluster_selection):
    payload = site_allocation_payload if command[1] == 'allocation' else site_payload
    if command[1] == 'show':
        payload['freshness']['source'] = 'scontrol'
    second_payload = {**deepcopy(payload), 'site_id': 'site-b', 'cluster_id': 'cluster-b'}
    with http_endpoint(lambda *_: (200, payload)) as (gateway, reads), http_endpoint(lambda *_: (200, second_payload)) as (second_gateway, second_reads):
        def central(call, count):
            if call['method'] == 'POST':
                return issuer(call, count)
            assert call['path'] in ['/v1/account/cli/sites/site-a/connection', '/v1/account/cli/sites/site-b/connection']
            assert call['bearer'] == 'Bearer identity-session-token' and call['capability'] is None
            selected = 'b' if '/site-b/' in call['path'] else 'a'
            return 200, {'schema_version': 'site.connection/v1', 'site_id': 'site-'+selected, 'cluster_id': 'cluster-'+selected,
                         'site_read_base_url': second_gateway if selected == 'b' else gateway, 'site_agent_secret': 'excluded'}
        with http_endpoint(central) as (portal, calls):
            config = tmp_path/'config.toml'
            config.write_text('[profiles.default]\nrequire_site_capability=true\n'+f'base_url={json.dumps(portal)}\n')
            config.chmod(0o600)
            original = config.read_bytes()
            for selected, expected in [('site-a', payload), ('site-b', second_payload)]:
                words = [*command, '--site', selected]
                cluster = expected['cluster_id']
                if cluster_selection == 'before':
                    words = ['--cluster', cluster, *words]
                elif cluster_selection == 'after':
                    words += ['--cluster', cluster]
                env = {'SAI_TOKEN': 'identity-session-token', 'XDG_CACHE_HOME': str(tmp_path / 'cache')}
                if cluster_selection == 'environment':
                    env['SAI_CLUSTER_ID'] = cluster
                output, error = StringIO(), StringIO()
                code = main(['--config', str(config), *words], environ=env, stdout=output, stderr=error)
                assert code == 0, error.getvalue()
                assert json.loads(output.getvalue()) == expected
            assert config.read_bytes() == original
            assert len(calls) == 4 and calls[1]['body']['cluster_id'] == 'cluster-a' and calls[3]['body']['cluster_id'] == 'cluster-b'
            assert calls[1]['body']['site_id'] == 'site-a' and calls[3]['body']['site_id'] == 'site-b'
            assert len(reads) == 1 and reads[0]['bearer'] is None
            assert reads[0]['capability'] == 'opaque-capability-2'
            assert len(second_reads) == 1 and second_reads[0]['bearer'] is None
            assert second_reads[0]['capability'] == 'opaque-capability-4'


def test_portable_cluster_constraint_rejects_mismatch_before_a_native_read(tmp_path):
    metadata = {'schema_version': 'site.connection/v1', 'site_id': 'site-a', 'cluster_id': 'cluster-a',
                'site_read_base_url': 'https://read.example.org'}
    with http_endpoint(lambda *_: (200, metadata)) as (portal, calls):
        config = tmp_path / 'config.toml'
        config.write_text('[profiles.default]\nrequire_site_capability=true\n' + f'base_url={json.dumps(portal)}\n')
        config.chmod(0o600)
        code, output, error = invoke(config, tmp_path, ['jobs', 'list', '--site', 'site-a', '--cluster', 'cluster-b'])
    assert code == 2 and output == '' and 'does not match' in error
    assert [call['path'] for call in calls] == ['/v1/account/cli/sites/site-a/connection']


def test_fixed_central_profile_retains_its_route_with_or_without_cluster_filter(tmp_path, job_payload):
    def reply(call, count):
        if call['method'] == 'POST':
            return issuer(call, count)
        assert call['path'].startswith('/v1/slurm/cli/jobs?')
        return 200, job_payload
    with http_endpoint(reply) as (portal, calls):
        config = tmp_path / 'config.toml'
        config.write_text('[profiles.default]\nsite_id="site-a"\ncluster_id="cluster-a"\n'
                          f'base_url={json.dumps(portal)}\nrequire_site_capability=true\n')
        config.chmod(0o600)
        for flags in ([], ['--cluster', 'cluster-a']):
            code, output, error = invoke(config, tmp_path, ['jobs', 'list', *flags])
            assert code == 0, error
            assert json.loads(output) == job_payload
    assert all('/connection' not in call['path'] for call in calls)


@pytest.mark.parametrize('change', [
    {'site_id': 'site-b'}, {'cluster_id': 'unsafe cluster'},
    {'site_read_base_url': 'http://read.example.org'}, {'site_read_base_url': 'https://user@read.example.org'},
    {'site_read_base_url': 'https://read.example.org/?'}, {'site_read_base_url': 'https://read.example.org/proxy'},
    {'site_read_base_url': 'https://read.example.org:bad'},
])
def test_bad_site_connection_never_issues_or_forwards_a_capability(tmp_path, change):
    payload = {'schema_version': 'site.connection/v1', 'site_id': 'site-a', 'cluster_id': 'cluster-a',
               'site_read_base_url': 'https://read.example.org', **change}
    with http_endpoint(lambda *_: (200, payload)) as (portal, calls):
        config = tmp_path/'config.toml'
        config.write_text('[profiles.default]\nrequire_site_capability=true\n'+f'base_url={json.dumps(portal)}\n')
        config.chmod(0o600)
        code, text, error = invoke(config, tmp_path, ['jobs', 'allocation', '12345', '--site', 'site-a'])
    assert code == 7 and text == ''
    assert len(calls) == 1 and calls[0]['method'] == 'GET'
    assert 'read.example.org' not in error


def test_cost_and_catalog_stay_central_when_native_job_origin_is_configured(tmp_path, running_estimate_payload):
    catalog = json.loads((Path(__file__).resolve().parents[1] / "contracts/site-resource-catalog/v1/catalog.json").read_text())
    catalog["site_id"] = "site-a"

    def central_reply(call, count):
        if call["method"] == "POST":
            return issuer(call, count)
        if "resource-catalog" in call["path"]:
            assert call["capability"] is None
            return 200, catalog
        if call['path'] == '/v1/account/cli/sites/site-a/connection':
            return 200, {'schema_version': 'site.connection/v1', 'site_id': 'site-a', 'cluster_id': 'cluster-a',
                         'site_read_base_url': None}
        assert call["path"].startswith("/v1/billing/cli/running-estimates?")
        return 200, running_estimate_payload

    with http_endpoint(central_reply) as (portal, central), http_endpoint(lambda *_: (503, {})) as (gateway, reads):
        config = profile(tmp_path, portal, gateway)
        for command in (["jobs", "cost"], ["resources", "catalog"]):
            result, _, errors = invoke(config, tmp_path, command)
            assert result == 0, errors
        config.write_text(config.read_text().replace('cluster_id="cluster-a"\n', ''))
        result, _, errors = invoke(config, tmp_path, ['jobs', 'cost'])
        assert result == 0, errors
    assert not reads
    assert all(c["bearer"] == "Bearer identity-session-token" for c in central)


@pytest.mark.parametrize("gateway_mode", [False, True])
def test_job_detail_must_match_the_requested_identifier(tmp_path, job_payload, site_payload, gateway_mode):
    payload = deepcopy(site_payload if gateway_mode else job_payload)
    payload["items"][0]["job_id"] = "another-job"
    if gateway_mode:
        payload["freshness"]["source"] = "scontrol"
        with http_endpoint(issuer) as (portal, _), http_endpoint(lambda *_: (200, payload)) as (gateway, _):
            result, output, _ = invoke(profile(tmp_path, portal, gateway), tmp_path, ["jobs", "show", "12345"])
    else:
        with http_endpoint(lambda *_: (200, payload)) as (portal, _):
            config = tmp_path / "config.toml"
            config.write_text(f'[profiles.default]\nsite_id="site-a"\nbase_url={json.dumps(portal)}\n')
            config.chmod(0o600)
            result, output, _ = invoke(config, tmp_path, ["jobs", "show", "12345"])
    assert result == 7 and output == ""
