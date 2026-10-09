from io import StringIO
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from sai_cli.cli import main
from sai_cli.local_quota import parse_quota_fields


@pytest.fixture
def native_quota(tmp_path):
    binary=tmp_path/'lfs'
    binary.write_text(f'#!{sys.executable}\n'+'''
import json,os,sys
from pathlib import Path
with Path(os.environ['NATIVE_CALL']).open('a') as out:
    out.write(json.dumps({'argv':sys.argv[1:],'uid':os.geteuid(),'locale':os.environ.get('LC_ALL'),
        'sai_token':'SAI_TOKEN' in os.environ})+'\\n')
mode=os.environ.get('NATIVE_MODE','valid')
if mode=='failure':
    print('private-native-detail',file=sys.stderr);raise SystemExit(13)
if sys.argv[1]=='project':
    value=b'0' if mode=='unassigned' else b'42001'
    sys.stdout.buffer.write(value+b' P '+os.fsencode(sys.argv[-1])+b'\\n')
else:
    if mode=='diagnostic': print('private-native-detail',file=sys.stderr)
    if mode=='replacement': os.replace(os.environ['REPLACEMENT'],sys.argv[-1])
    print(os.environ.get('QUOTA_FIELDS','1024|2048|4096|-|64|100|200|6d23h59m|'))
''')
    binary.chmod(0o755)
    target=tmp_path/'quota-target';target.mkdir()
    env={'PATH':str(tmp_path),'NATIVE_CALL':str(tmp_path/'calls.jsonl'),
         'SAI_MANAGED_LOGIN_NODE':'1','SAI_CONFIG':str(tmp_path/'absent-config'),
         'SAI_TOKEN':'test-token','LC_ALL':'invalid-locale'}
    return env,target


def invoke(env,*args):
    out,err=StringIO(),StringIO()
    code=main(list(args),environ=env,stdout=out,stderr=err)
    return code,out.getvalue(),err.getvalue()


def test_local_path_uses_native_metadata_and_selected_counter_fields_without_portal(native_quota,monkeypatch):
    env,target=native_quota
    monkeypatch.setattr('sai_cli.cli._build_transport',lambda *a:pytest.fail('remote transport'))
    code,out,err=invoke(env,'storage','local-quota',str(target))
    assert code==0 and not err
    value=json.loads(out)
    assert value['schema_version']=='native.quota/v1' and value['coverage']=='filesystem_project'
    assert value['native_project_id']==42001 and value['used_bytes']=='1048576'
    assert value['block_soft_bytes']=='2097152' and value['block_hard_bytes']=='4194304'
    assert value['used_inodes']=='64' and value['inode_grace']['remaining_seconds']==604740
    calls=[json.loads(line) for line in Path(env['NATIVE_CALL']).read_text().splitlines()]
    assert len(calls)==2 and calls[0]['argv']==['project','-d','--',str(target)]
    assert calls[1]['argv'][:4]==['quota','-p','42001','-q']
    assert '--delimiter=|' in calls[1]['argv'] and '--filesystem' not in calls[1]['argv']
    assert all(call['uid']==os.geteuid() and call['locale']=='C' and not call['sai_token'] for call in calls)


@pytest.mark.parametrize('name',['space name','汉字配额','-leading','line\nbreak','tab\tname',"quote'and;dollar$()",'escape\x1b[31m'])
def test_native_paths_are_not_identifier_tokens_or_shell_programs(native_quota,tmp_path,name):
    env,_=native_quota
    target=tmp_path/name;target.write_text('unchanged')
    code,out,err=invoke(env,'storage','local-quota','--',str(target))
    assert code==0 and not err and json.loads(out)['path']==str(target)
    code,table,err=invoke(env,'storage','local-quota','--format','table','--',str(target))
    assert code==0 and not err and '\x1b' not in table
    assert target.read_text()=='unchanged'


def test_native_byte_filename_round_trips_through_json(native_quota,tmp_path):
    env,_=native_quota
    raw=os.fsencode(tmp_path)+b'/native-\xff-name'
    with open(raw,'wb') as handle:handle.write(b'unchanged')
    path=os.fsdecode(raw)
    code,out,err=invoke(env,'storage','local-quota',path)
    assert code==0 and not err and os.fsencode(json.loads(out)['path'])==raw
    assert out.isascii()


def test_default_current_directory_and_symlink_target(native_quota,tmp_path,monkeypatch):
    env,target=native_quota;monkeypatch.chdir(target)
    code,out,err=invoke(env,'storage','local-quota')
    assert code==0 and not err and json.loads(out)['path']=='.'
    link=tmp_path/'alias';link.symlink_to(target,target_is_directory=True)
    code,out,err=invoke(env,'storage','local-quota',str(link))
    assert code==0 and not err and json.loads(out)['resolved_path']==str(target)


@pytest.mark.parametrize('mode,expected', [('unassigned',5),('failure',6),('diagnostic',6)])
def test_missing_project_or_failed_source_is_not_zero_or_success(native_quota,mode,expected):
    env,target=native_quota;env['NATIVE_MODE']=mode
    code,out,err=invoke(env,'storage','local-quota',str(target))
    assert code==expected and not out and 'private-native-detail' not in err
    if mode=='unassigned':assert len(Path(env['NATIVE_CALL']).read_text().splitlines())==1


def test_changed_target_cannot_relabel_another_objects_quota(native_quota,tmp_path):
    env,target=native_quota
    replacement=tmp_path/'replacement';replacement.mkdir()
    env.update(NATIVE_MODE='replacement',REPLACEMENT=str(replacement))
    code,out,err=invoke(env,'storage','local-quota',str(target))
    assert code==6 and not out and json.loads(err)['error']['code']=='native_target_changed'


@pytest.mark.parametrize('fields',[
    '1|2|3|-|4|5|6|-|\n1|2|3|-|4|5|6|-|',
    '[1024]|2|3|-|4|5|6|-|','1G|2|3|-|4|5|6|-|','1|2|3|unknown|4|5|6|-|',
    '-1|2|3|-|4|5|6|-|',str(2**64)+'|2|3|-|4|5|6|-|','1|2|3|-|4|5|6|-',
])
def test_partial_or_malformed_counters_fail_before_output(native_quota,fields):
    env,target=native_quota;env['QUOTA_FIELDS']=fields
    code,out,err=invoke(env,'storage','local-quota',str(target))
    assert code==7 and not out and json.loads(err)['error']['code']=='native_response_invalid'


def test_exact_large_counters_zero_limits_and_grace_states(native_quota):
    env,target=native_quota
    value=parse_quota_fields(b'9007199254740993*|0|0|expired|64|0|0|notify|\n')
    assert value['used_bytes']==str(9007199254740993*1024)
    assert value['native_usage_markers']['space'] and value['block_grace']['state']=='expired'
    assert value['inode_grace']['state']=='notify'
    env['QUOTA_FIELDS']='0|0|0|-|0|0|0|-|'
    code,table,err=invoke(env,'storage','local-quota','--format','table',str(target))
    assert code==0 and not err and '0 B' in table and 'unlimited' in table
    assert 'Disk quotas for project 42001' in table and 'Scope: filesystem project' not in table
    assert all(heading in table for heading in ('used', 'quota', 'limit', 'grace', 'files'))


@pytest.mark.parametrize('prefix,suffix',[(['--timeout','1'],[]),([],['--timeout','1'])])
def test_timeout_works_before_command_and_after_leaf(native_quota,prefix,suffix):
    env,target=native_quota
    assert invoke(env,*prefix,'storage','local-quota',str(target),*suffix)[0]==0


def test_nonexistent_path_and_remote_options_fail_without_native_call(native_quota,tmp_path):
    env,target=native_quota
    assert invoke(env,'storage','local-quota',str(tmp_path/'absent'))[0]==5
    assert invoke(env,'--site','site-other','storage','local-quota',str(target))[0]==2
    assert not Path(env['NATIVE_CALL']).exists()


def test_cold_quota_process_does_not_load_slurm_or_remote_clients(native_quota):
    env,target=native_quota
    program='''
import io,json,sys
from sai_cli.cli import main
out,err=io.StringIO(),io.StringIO()
assert main(['storage','local-quota',sys.argv[1]],stdout=out,stderr=err)==0,err.getvalue()
assert json.loads(out.getvalue())['authority']=='native'
for name in ('sai_cli.auth','sai_cli.client','sai_cli.local_jobs','sai_cli.local_resources','sai_cli.config','ssl','http.client'):
    assert name not in sys.modules,name
'''
    done=subprocess.run([sys.executable,'-c',program,str(target)],env={**os.environ,**env},
                         capture_output=True,text=True,timeout=5)
    assert done.returncode==0,done.stderr
