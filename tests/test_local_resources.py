from copy import deepcopy
from io import StringIO
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from sai_cli.cli import main
from sai_cli.local_resources import _gpu_counts, _gpu_total, render_local_resources, LocalResources


def number(value, *, present=True):
    return {"set": present, "infinite": False, "number": value}


def node(name='node-a', partition='gpu-new', *, gpu=True, down=False):
    return {
        'nodes': {'nodes': [name]}, 'node': {'state': ['DOWN', 'NOT_RESPONDING'] if down else ['MIXED']},
        'cpus': {'total': 32, 'allocated': 0 if down else 8, 'idle': 0 if down else 24,
                 'other': 32 if down else 0, 'load': {'minimum': 730, 'maximum': 730}},
        'memory': {'minimum': 65536, 'maximum': 65536, 'allocated': 0 if down else 16384,
                   'free': {'minimum': number(30000), 'maximum': number(30000)}},
        'gres': {'total': 'gpu:example:4(S:0-1)' if gpu else '',
                 'used': ('gpu:example:0(IDX:N/A)' if down else 'gpu:example:2(IDX:N/A)') if gpu else ''},
        'resource_spec': {'cpus':'','memory':0},
        'partition': {'name': partition, 'partition': {'state': ['UP']},
                      'qos': {'allowed': 'normal,special', 'deny': '', 'assigned': ''},
                      'accounts': {'allowed': 'private-account'}, 'tres': {'billing_weights': 'secret-price'}},
        'reason': {'description': 'private-reason'}, 'addresses': ['private-address'],
    }


@pytest.fixture
def native_client(tmp_path):
    payload = {'meta': {'slurm': {'cluster': 'cluster-a'}}, 'errors': [], 'warnings': [],
               'sinfo': [node(), node('node-b', down=True), node('node-c', 'cpu-new', gpu=False)]}
    path = tmp_path/'payload.json'
    path.write_text(json.dumps(payload))
    binary = tmp_path/'sinfo'
    binary.write_text(f'#!{sys.executable}\n' + '''
import json, os, sys
from pathlib import Path
with Path(os.environ['NATIVE_CALL']).open('a') as output:
    output.write(json.dumps({'argv':sys.argv[1:], 'uid':os.geteuid(),
        'sai_token':'SAI_TOKEN' in os.environ, 'sinfo_partition':'SINFO_PARTITION' in os.environ,
        'slurm_conf':os.environ.get('SLURM_CONF')})+'\\n')
print(Path(os.environ['NATIVE_PAYLOAD']).read_text())
''')
    binary.chmod(0o755)
    env = {'PATH':str(tmp_path), 'NATIVE_PAYLOAD':str(path), 'NATIVE_CALL':str(tmp_path/'calls.jsonl'),
           'SAI_MANAGED_LOGIN_NODE':'1', 'SAI_CONFIG':str(tmp_path/'not-present'), 'SAI_TOKEN':'test-token',
           'SINFO_PARTITION':'unexpected', 'SLURM_CONF':'native-config'}
    return env, path, payload


def invoke(env, *args):
    output, errors = StringIO(), StringIO()
    code = main(list(args), environ=env, stdout=output, stderr=errors)
    return code, output.getvalue(), errors.getvalue()


def result(native_client, *args):
    code, output, errors = invoke(native_client[0], 'resources', 'local', *args)
    assert code == 0 and not errors, errors
    return json.loads(output)


def test_one_local_read_has_no_portal_prerequisite_or_native_credentials_leak(native_client, monkeypatch):
    monkeypatch.setattr('sai_cli.cli._build_transport', lambda *a: pytest.fail('HTTP requested'))
    value = result(native_client)
    assert value['schema_version'] == 'native.resources/v1' and value['authority'] == 'native'
    calls = Path(native_client[0]['NATIVE_CALL']).read_text().splitlines()
    assert len(calls) == 1
    call = json.loads(calls[0])
    assert call['argv'] == ['--json', '--local', '--Node'] and call['uid'] == os.geteuid()
    assert not call['sai_token'] and not call['sinfo_partition'] and call['slurm_conf'] == 'native-config'
    assert 'private-' not in json.dumps(value) and 'secret-price' not in json.dumps(value)


def test_gpu_counts_use_quantities_not_indices_and_down_nodes_are_not_busy(native_client):
    value = result(native_client, '--kind', 'gpu')
    summary = value['summary']
    assert summary['nodes'] == 2 and summary['ready_nodes'] == 1
    assert summary['gpu'] == {'capacity':8, 'allocated':2, 'free_on_ready_nodes':2,
                               'blocked_unallocated':4, 'largest_free_on_one_node':2}
    down = next(item for item in value['nodes'] if item['name'] == 'node-b')
    assert down['reported']['cpu_load_hundredths'] is None and down['reported']['free_memory_mib'] is None
    assert down['gpu']['allocated_units'] == 0


def test_cpu_fields_separate_scheduler_residual_from_reported_free_memory(native_client):
    value = result(native_client, '--kind', 'cpu')
    assert [item['name'] for item in value['nodes']] == ['node-c']
    assert value['summary']['cpu']['free_on_ready_nodes'] == 24
    item = value['nodes'][0]
    assert item['memory']['unallocated_mib'] == 49152
    assert item['reported'] == {'cpu_load_hundredths':730, 'free_memory_mib':30000, 'sampled_at':None}


def test_same_node_in_two_partitions_is_counted_once_globally(native_client):
    env, path, payload = native_client
    other = deepcopy(payload['sinfo'][0])
    other['partition']['name'] = 'gpu-other'
    other['partition']['partition']['state'] = ['DOWN']
    payload['sinfo'].append(other)
    path.write_text(json.dumps(payload))
    value = result(native_client, '--kind', 'gpu')
    assert value['summary']['nodes'] == 2 and value['summary']['gpu']['capacity'] == 8
    down = next(part for part in value['partitions'] if part['name'] == 'gpu-other')
    assert down['summary']['gpu']['allocated'] == 2
    assert down['summary']['gpu']['free_on_ready_nodes'] == 0
    assert down['summary']['gpu']['blocked_unallocated'] == 2
    assert value['summary']['gpu']['free_on_ready_nodes'] == 2


@pytest.mark.parametrize('field', ['gpu', 'cpu', 'memory', 'state'])
def test_unknown_observations_never_become_available_capacity(native_client, field):
    env, path, payload = native_client
    payload['sinfo'] = [node()]
    item = payload['sinfo'][0]
    if field == 'gpu': item['gres']['total'] = None
    elif field == 'cpu': item['cpus']['idle'] = None
    elif field == 'memory': item['memory'].update(minimum=None, maximum=None)
    else: item['node']['state'] = ['FUTURE_UNKNOWN_STATE']
    path.write_text(json.dumps(payload))
    value = result(native_client)
    family = 'gpu' if field == 'state' else field
    assert value['summary'][family]['free_on_ready_nodes'] is None
    if field == 'gpu': assert value['unclassified_nodes'] == 1


def test_down_cpu_other_slots_remain_blocked_not_free(native_client):
    env, path, payload = native_client
    payload['sinfo'] = [node('cpu-a', 'cpu-new', gpu=False, down=True)]
    path.write_text(json.dumps(payload))
    summary = result(native_client)['summary']['cpu']
    assert summary['capacity'] == summary['blocked_unallocated'] == 32
    assert summary['allocated'] == summary['free_on_ready_nodes'] == 0


@pytest.mark.parametrize('gres,expected', [
    ('gpu:4',4), ('gpu:example:4(S:0-1)',4),
    ('gpu:type-a:2(IDX:0-1),gpu:type-b:3(IDX:2-4)',5),
    ('gpu:5,gpu:type-a:2,gpu:type-b:3',5),
    ('gpu:example:2(IDX:N/A),mps:100(CNT:100)',2),
    ('shard:100(0/100)',0), ('',0), ('(null)',0),
    ('gpu:example:bad',None), ('gpu::4',None), ('N/A',None), (None,None),
])
def test_typed_and_shared_gres_do_not_invent_physical_device_counts(gres, expected):
    assert _gpu_total(_gpu_counts(gres)) == expected


def test_native_cpu_and_memory_reservations_are_not_advertised_as_free(native_client):
    env,path,payload=native_client
    row=node('cpu-reserved','cpu-new',gpu=False)
    row['resource_spec']={'cpus':'0-3,8-11','memory':4096}
    payload['sinfo']=[row];path.write_text(json.dumps(payload))
    value=result(native_client)
    assert value['nodes'][0]['cpu']['total']==32
    assert value['summary']['cpu']['capacity']==24
    assert value['summary']['cpu']['free_on_ready_nodes']==16
    assert value['summary']['memory']['capacity']==61440
    assert value['summary']['memory']['free_on_ready_nodes']==45056


@pytest.mark.parametrize('arguments,expected', [
    (['gpu-new'], ['--partition=gpu-new']),
    (['--partition','gpu-new,cpu-new','--node','node-[a,b]'], ['--partition=gpu-new,cpu-new','--nodes=node-[a,b]']),
])
def test_native_filters_and_positional_legacy_partition(native_client, arguments, expected):
    result(native_client, *arguments)
    call=json.loads(Path(native_client[0]['NATIVE_CALL']).read_text())
    assert call['argv'] == ['--json','--local','--Node',*expected]


@pytest.mark.parametrize('args', [
    ['--site','other','resources','local'], ['resources','local','gpu-a','-p','gpu-b'],
    ['resources','local','--timeout','0'], ['resources','local','--node','bad\nvalue'],
])
def test_invalid_intent_fails_before_native_io(native_client, args):
    code, output, error=invoke(native_client[0],*args)
    assert code==2 and not output and json.loads(error)['error']['code']=='configuration_invalid'
    assert not Path(native_client[0]['NATIVE_CALL']).exists()


@pytest.mark.parametrize('defect', ['grouped','conflict','invalid_number','native_error'])
def test_invalid_source_never_silently_drops_nodes(native_client, defect):
    env,path,payload=native_client
    if defect=='grouped':payload['sinfo'][0]['nodes']['nodes'].append('extra-node')
    elif defect=='conflict':
        extra=deepcopy(payload['sinfo'][0]);extra['cpus']['total']=99;payload['sinfo'].append(extra)
    elif defect=='invalid_number':payload['sinfo'][0]['memory']['allocated']=True
    else:payload['errors']=[{'description':'private-provider-detail'}]
    path.write_text(json.dumps(payload))
    code,output,error=invoke(env,'resources','local')
    assert code in {6,7} and not output and 'private-provider-detail' not in error


def test_summary_default_details_on_demand_and_narrow_readability(native_client):
    value=result(native_client, '--kind','gpu')
    plain=render_local_resources(LocalResources(value),width=40)
    detailed=render_local_resources(LocalResources(value),details=True,width=40)
    assert 'node-a' not in plain and 'node-a' in detailed
    assert 'GPU units' in plain and 'blocked idle' in plain and 'largest' in plain
    assert 'utilization' in plain and 'Usage Matrix' not in detailed
    assert all(len(line)<=40 for line in detailed.splitlines())
    assert '\x1b' not in plain
    code,table,error=invoke(native_client[0],'resources','local','gpu-new','--format','table')
    assert code==0 and not error and 'node-a' in table


def test_empty_native_data_is_not_a_source_failure(native_client):
    env,path,payload=native_client;payload['sinfo']=[];path.write_text(json.dumps(payload))
    value=result(native_client)
    assert value['nodes']==[] and value['summary']['nodes']==0


def test_fresh_resource_process_does_not_load_jobs_or_remote_product_clients(native_client):
    program='''
import io,json,sys
from sai_cli.cli import main
out,err=io.StringIO(),io.StringIO()
assert main(['resources','local'],stdout=out,stderr=err)==0,err.getvalue()
assert json.loads(out.getvalue())['source']=='sinfo'
for name in ('sai_cli.auth','sai_cli.client','sai_cli.local_jobs','sai_cli.config','ssl','http.client'):
    assert name not in sys.modules,name
'''
    done=subprocess.run([sys.executable,'-c',program],env={**os.environ,**native_client[0]},
                         capture_output=True,text=True,timeout=5)
    assert done.returncode==0,done.stderr
