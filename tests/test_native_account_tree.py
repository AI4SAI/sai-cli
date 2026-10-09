from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

from test_local_jobs import invoke, native_client, native_job


@pytest.fixture
def tree_client(native_client):
    env, path, payload = native_client
    directory = path.parent
    env.update(TREE_CALLS=str(directory/'tree-calls.jsonl'),
               TREE_ROWS='cluster-a|research|alice|/research/0-alice/\n'
                         'cluster-a|project-a|alice|/research/project-a/0-alice/\n'
                         'cluster-a|project-a|bob|/research/project-a/0-bob/\n',
               SACCTMGR_CLUSTERS='wrong-cluster', SCONTROL_FUTURE='1')
    program = f'#!{sys.executable}\n' + '''
import json,os,sys
from pathlib import Path
name=Path(sys.argv[0]).name
with Path(os.environ['TREE_CALLS']).open('a') as output:
    output.write(json.dumps({'name':name,'argv':sys.argv[1:],
        'uid':os.geteuid(),'slurm_conf':os.environ.get('SLURM_CONF'),
        'unexpected_env':any(k.startswith(('SAI_','_SAI_','SQUEUE_','SACCTMGR_','SCONTROL_')) for k in os.environ)})+'\\n')
if name=='scontrol':
    print(json.dumps({'meta':{'slurm':{'cluster':'cluster-a'}},'errors':[],'warnings':[]}))
else:
    mode=os.environ.get('TREE_SCENARIO')
    if mode in ('stderr','failure'):
        print('provider-private-detail',file=sys.stderr)
        if mode=='failure':raise SystemExit(1)
    if mode=='oversize':print('x'*1100000)
    else:sys.stdout.write(os.environ['TREE_ROWS'])
'''
    for name in ('scontrol','sacctmgr'):
        binary=directory/name
        binary.write_text(program)
        binary.chmod(0o755)
    child=deepcopy(payload['jobs'][0])
    child.update(job_id=43,account='project-a',user_name='bob')
    payload['jobs'].append(child)
    path.write_text(json.dumps(payload))
    return env,path,payload


def test_subtree_uses_native_expansion_and_one_scoped_queue_read(tree_client):
    env,_,_=tree_client
    code,raw,error=invoke(env,'jobs','local','-A','research','--with-subaccounts')
    assert code==0 and not error
    result=json.loads(raw)
    assert result['count']==2 and result['filters']['users'] is None
    assert result['filters']['accounts']=='project-a,research'
    assert result['filters']['account_root']=='research'
    calls=[json.loads(line) for line in Path(env['TREE_CALLS']).read_text().splitlines()]
    assert calls[0]['argv']==['--json','ping']
    assert calls[1]['argv']==['-nP','show','assoc','WithSubAccounts','where','cluster=cluster-a',
                             'account=research','format=Cluster,Account,User,Lineage']
    assert not any(call['unexpected_env'] for call in calls)
    assert all(call['slurm_conf']=='native-slurm.conf' for call in calls)
    queue=json.loads(Path(env['NATIVE_CALL']).read_text())
    assert queue['argv']==['--json','--local','--account=project-a,research']
    assert all(call['uid']==queue['uid'] for call in calls)
    assert 'Lineage' not in raw and 'provider-private-detail' not in raw


def test_explicit_project_subtree_does_not_expand_to_parent_or_sibling(tree_client):
    env,path,payload=tree_client
    env['TREE_ROWS']='cluster-a|project-a|alice|/research/project-a/0-alice/\n'
    payload['jobs']=payload['jobs'][1:];path.write_text(json.dumps(payload))
    code,raw,error=invoke(env,'jobs','local','--with-subaccounts','-A','project-a','-u','bob','-t','R')
    assert code==0 and not error
    result=json.loads(raw)
    assert result['filters']['accounts']=='project-a'
    assert result['filters']['account_root']=='project-a'
    assert result['filters']['users']=='bob' and result['filters']['states']=='R'


def test_parent_row_can_be_hidden_while_native_child_lineage_identifies_subtree(tree_client):
    env,_,_=tree_client
    env['TREE_ROWS']='cluster-a|project-a|alice|/research/project-a/0-alice/\n'
    code,raw,error=invoke(env,'jobs','local','-A','research','--with-subaccounts')
    assert code==0 and not error and json.loads(raw)['filters']['accounts']=='project-a,research'


@pytest.mark.parametrize('rows',[
    '',
    'cluster-b|research|alice|/research/0-alice/\n',
    'cluster-a|project-a|alice|/research-other/project-a/0-alice/\n',
    'cluster-a|project-a|alice|/research/not-project-a/0-alice/\n',
    'cluster-a|research|alice|/research/0-bob/\n',
    'cluster-a|research,other|alice|/research/0-alice/\n',
    'cluster-a|research|alice|/research/0-alice/|extra\n',
    'cluster-a|research|alice|/research/0-alice/\x1b\n',
    'cluster-a|project-a|alice|/research/project-a/0-alice/\n'
    'cluster-a|project-a|bob|/research/other/project-a/0-bob/\n',
])
def test_invalid_or_missing_hierarchy_never_falls_back_to_a_broader_or_partial_queue(tree_client,rows):
    env,_,_=tree_client;env['TREE_ROWS']=rows
    code,raw,error=invoke(env,'jobs','local','-A','research','--with-subaccounts')
    assert code in (6,7) and not raw
    assert not Path(env['NATIVE_CALL']).exists()
    assert json.loads(error)['error']['code'] in ('native_response_invalid','native_account_tree_unavailable')


@pytest.mark.parametrize('arguments',[
    ['--with-subaccounts'],['-A','research,other','--with-subaccounts'],
    ['-A','research/other','--with-subaccounts'],['-A','research|other','--with-subaccounts'],
])
def test_subtree_intent_requires_one_account_before_native_io(tree_client,arguments):
    env,_,_=tree_client
    code,raw,error=invoke(env,'jobs','local',*arguments)
    assert code==2 and not raw
    assert not Path(env['TREE_CALLS']).exists() and not Path(env['NATIVE_CALL']).exists()


@pytest.mark.parametrize('mode',['failure','stderr','oversize'])
def test_incomplete_native_metadata_is_a_bounded_failure(tree_client,mode):
    env,_,_=tree_client;env['TREE_SCENARIO']=mode
    code,raw,error=invoke(env,'jobs','local','-A','research','--with-subaccounts')
    assert code in (6,7) and not raw and 'provider-private-detail' not in error
    assert not Path(env['NATIVE_CALL']).exists()


@pytest.mark.parametrize('defect',['cluster','account'])
def test_queue_must_match_resolved_cluster_and_subtree(tree_client,defect):
    env,path,payload=tree_client
    if defect=='cluster':payload['meta']['slurm']['cluster']='cluster-b'
    else:payload['jobs'][0]['account']='unrelated'
    path.write_text(json.dumps(payload))
    code,raw,error=invoke(env,'jobs','local','-A','research','--with-subaccounts')
    assert code==7 and not raw and json.loads(error)['error']['code']=='native_response_invalid'


def test_exact_account_query_keeps_its_single_native_call(tree_client):
    env,_,_=tree_client
    code,raw,error=invoke(env,'jobs','local','-A','research')
    assert code==0 and not error and 'account_root' not in json.loads(raw)['filters']
    assert not Path(env['TREE_CALLS']).exists()
    assert json.loads(Path(env['NATIVE_CALL']).read_text())['argv']==['--json','--local','--account=research']
