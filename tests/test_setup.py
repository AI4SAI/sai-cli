from io import StringIO
import json
import os
from pathlib import Path
import stat
import shlex
import tomllib

import pytest

from sai_cli.cli import main
from sai_cli.errors import ConfigError
from sai_cli.setup import _create_profile
from test_site_transport import http_endpoint
from test_cli_auth import _server


def settings(issuer):
    return {"schema_version":"cli.connection/v1", "identity_issuer":issuer,
            "oidc_client_id":"sai-cli", "oidc_resource":"sai-portal", "require_site_capability":True}


def invoke(tmp_path, *args, env=None):
    output, errors = StringIO(), StringIO()
    environment = {"XDG_CONFIG_HOME":str(tmp_path/'config'),"XDG_DATA_HOME":str(tmp_path/'data'),
                   "XDG_CACHE_HOME":str(tmp_path/'cache'), **(env or {})}
    code=main(list(args),environ=environment,stdout=output,stderr=errors)
    return code,output.getvalue(),errors.getvalue()


def test_first_use_configuration_then_real_device_flow_without_secret_copy(tmp_path,monkeypatch):
    monkeypatch.setenv('NO_PROXY','127.0.0.1,localhost')
    with _server() as (identity,auth):
        def respond(call,_):
            assert call['path']=='/v1/auth/config?client=sai-cli'
            assert call['bearer'] is None and call['capability'] is None
            return 200,{**settings(identity),'password':'never copied','site_read_base_url':'https://ignored.example.org'}
        with http_endpoint(respond) as (portal,calls):
            code,text,error=invoke(tmp_path,'configure',portal,env={'SAI_TOKEN':'unused-user-token'})
            assert code==0,error
            result=json.loads(text);path=Path(result['config_path'])
            assert result['created'] is True
            assert stat.S_IMODE(path.stat().st_mode)==0o600
            assert stat.S_IMODE(path.parent.stat().st_mode)==0o700
            content=path.read_bytes();profile=tomllib.loads(content.decode())['profiles']['default']
            assert profile['oidc_scope']=='openid offline_access sai.compute.read'
            assert not {'site_id','cluster_id','password','site_read_base_url'} & profile.keys()
            code,text,error=invoke(tmp_path,'configure',portal)
            assert code==0 and not json.loads(text)['created'] and path.read_bytes()==content
            assert all(request['path']=='/.well-known/openid-configuration' for request in auth.requests)
            code,text,error=invoke(tmp_path,'auth','login','--no-wait')
            assert code==0,error
            assert set(auth.requested_scope.split())=={'openid','offline_access','sai.compute.read'}
            code,text,error=invoke(tmp_path,'auth','login','--resume')
            assert code==0 and json.loads(text)['authenticated'],error
            assert 'opaque-refresh-token' not in path.read_text()
            assert len(calls)==2


@pytest.mark.parametrize('prefix',[False,True])
def test_config_profile_options_keep_argument_order_and_existing_bytes(tmp_path,monkeypatch,prefix):
    monkeypatch.setenv('NO_PROXY','127.0.0.1,localhost')
    config=tmp_path/'chosen.toml'
    with _server() as (identity,_),http_endpoint(lambda *_:(200,settings(identity))) as (origin,_):
        flags=['--config',str(config),'--profile','work'];command=['configure',origin]
        code,text,error=invoke(tmp_path,*(flags+command if prefix else command+flags))
        assert code==0,error
        assert tomllib.loads(config.read_text())['default_profile']=='work'
        content=config.read_bytes()+b'\n# custom setting\nsite_id = "site-a"\n'
        config.write_bytes(content)
        assert invoke(tmp_path,*(command+flags))[0]==0
        assert config.read_bytes()==content
        config.write_text('[profiles.work]\nbase_url="https://previous.example.org"\n')
        before=config.read_bytes()
        code,text,error=invoke(tmp_path,*(command+flags))
        assert code==2 and not text and 'configuration_exists' in error
        assert config.read_bytes()==before


@pytest.mark.parametrize('change',[{'schema_version':'wrong'},{'oidc_client_id':'other'},
    {'oidc_resource':'unsafe\nvalue'},{'require_site_capability':False},{'identity_issuer':'https://id.example.org?token=x'}])
def test_untrusted_connection_metadata_never_creates_a_profile(tmp_path,monkeypatch,change):
    monkeypatch.setenv('NO_PROXY','127.0.0.1,localhost')
    with http_endpoint(lambda *_:(200,{**settings('https://id.example.org'),**change})) as (origin,calls):
        code,text,error=invoke(tmp_path,'configure',origin)
        assert code in {2,7} and not text
        assert not (tmp_path/'config/sai/config.toml').exists()
        assert len(calls)==1


def test_unsafe_config_managed_install_and_native_flags_fail_before_network(tmp_path,monkeypatch):
    monkeypatch.setattr('sai_cli.transport.JsonTransport.request',lambda *a,**k:pytest.fail('unexpected network'))
    assert invoke(tmp_path,'configure','https://example.org',env={'SAI_MANAGED_LOGIN_NODE':'1'})[0]==2
    assert invoke(tmp_path,'configure','https://example.org','--site','site-a')[0]==2
    target=tmp_path/'config/sai/config.toml';target.parent.mkdir(parents=True)
    target.symlink_to(tmp_path/'missing')
    assert invoke(tmp_path,'configure','https://example.org')[0]==2
    target.unlink();target.write_text('[profiles.default]\n');target.chmod(0o666)
    assert invoke(tmp_path,'configure','https://example.org')[0]==2


def test_configure_discovery_lists_only_accepted_connection_inputs(tmp_path):
    code,text,error=invoke(tmp_path,'describe','configure')
    assert code==0,error
    operation=json.loads(text)['operations'][0]
    assert operation['effect']=='local_file_write' and operation['required_scopes']==[]
    assert {p['name'] for p in operation['parameters']}=={'config','profile','timeout','service_url','format'}


def test_profile_publish_never_replaces_a_concurrent_writer(tmp_path,monkeypatch):
    destination=tmp_path/'config.toml';link=os.link
    def competing(source,target):
        Path(target).write_text('concurrent profile')
        link(source,target)
    monkeypatch.setattr('sai_cli.setup.os.link',competing)
    with pytest.raises(ConfigError,match='concurrently'):
        _create_profile(destination,'proposed')
    assert destination.read_text()=='concurrent profile'
    assert list(tmp_path.iterdir())==[destination]


def test_failed_discovery_and_oversized_metadata_leave_no_config(tmp_path,monkeypatch):
    monkeypatch.setenv('NO_PROXY','127.0.0.1,localhost')
    with http_endpoint(lambda *_:(503,{'detail':{'code':'upstream_unavailable'}})) as (identity,_):
        with http_endpoint(lambda *_:(200,settings(identity))) as (origin,_):
            code,text,error=invoke(tmp_path,'configure',origin)
            assert code==6 and not text and not (tmp_path/'config/sai/config.toml').exists()
    with http_endpoint(lambda *_:(200,{**settings('https://id.example.org'),'extra':'x'*16384})) as (origin,_):
        code,text,error=invoke(tmp_path,'configure',origin)
        assert code==7 and not text and not (tmp_path/'config/sai/config.toml').exists()


def test_first_use_never_claims_success_with_another_effective_connection(tmp_path,monkeypatch):
    from sai_cli.cli import build_parser
    from sai_cli.config import resolve_settings
    monkeypatch.setenv('NO_PROXY','127.0.0.1,localhost')
    with _server() as (identity,_), http_endpoint(lambda *_:(200,settings(identity))) as (service,_):
        destination=tmp_path/'config/sai/config.toml'
        for overrides in ({'SAI_API_BASE_URL':'https://previous.example.org'},
                          {'SAI_IDENTITY_ISSUER':'https://other.example.org'},
                          {'SAI_OIDC_CLIENT_ID':'old-client'},
                          {'SAI_OIDC_RESOURCE':'old-resource'},
                          {'SAI_OIDC_SCOPE':'openid offline_access'},
                          {'SAI_REQUIRE_SITE_CAPABILITY':'false'}):
            code,text,error=invoke(tmp_path,'configure',service,env=overrides)
            assert code==2 and not text and not destination.exists()
            assert 'configuration_environment_conflict' in error
            assert next(iter(overrides)) in error
            assert next(iter(overrides.values())) not in json.loads(error)['error']['message']
        matching={'SAI_API_BASE_URL':service+'/', 'SAI_IDENTITY_ISSUER':identity+'/',
                  'SAI_REQUIRE_SITE_CAPABILITY':'true'}
        code,text,error=invoke(tmp_path,'configure',service,env=matching)
        assert code==0,error
        actual=resolve_settings(build_parser().parse_args(['sites']),
                                {'XDG_CONFIG_HOME':str(tmp_path/'config'),**matching},require_site=False)
        assert actual.base_url==service and actual.identity_issuer.rstrip('/')==identity
        original=destination.read_bytes()
        assert invoke(tmp_path,'configure',service,env={'SAI_API_BASE_URL':'https://previous.example.org'})[0]==2
        assert destination.read_bytes()==original


def test_first_use_errors_lead_through_configure_and_site_discovery(tmp_path):
    config = tmp_path / 'selected service.toml'
    flags = ['--config', str(config), '--profile', 'work', '--cache', str(tmp_path / 'tokens.json')]
    code, output, error = invoke(tmp_path, 'status', *flags)
    assert code == 2 and not output
    configure = shlex.split(json.loads(error)['error']['message'].split('`')[1])
    assert configure[:3] == ['sai', 'configure', 'SERVICE_URL'] and '--cache' not in configure
    assert configure[configure.index('--config') + 1] == str(config)
    assert configure[configure.index('--profile') + 1] == 'work'
    directory = {'schema_version': 'site.directory/v1', 'source': 'portal_published_sites',
                 'queried_at': '2026-10-01T00:00:00Z', 'items': [{'site_id': 'site-a', 'display_name': 'Research'}],
                 'count': 1, 'has_more': False, 'next_cursor': None}
    with _server() as (identity, _):
        def reply(call, _):
            if call['path'] == '/v1/auth/config?client=sai-cli':
                assert call['bearer'] is None
                return 200, settings(identity)
            assert call['path'] == '/v1/account/cli/sites?limit=50'
            return 200, directory
        with http_endpoint(reply) as (origin, calls):
            configure[2] = origin
            assert invoke(tmp_path, *configure[1:])[0] == 0
            env = {'SAI_TOKEN': 'test-user'}
            code, output, error = invoke(tmp_path, 'status', *flags, env=env)
            assert code == 2 and not output and len(calls) == 1
            sites = shlex.split(json.loads(error)['error']['message'].split('`')[1])
            code, output, error = invoke(tmp_path, *sites[1:], env=env)
            assert code == 0 and 'Research' in output, error
            assert len(calls) == 2
