"""Real native subprocesses share the installed gateway parser, without OAuth."""
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest
from test_local_jobs import native_client, native_job, invoke


@pytest.fixture
def topology_client(native_client):
    env, path, payload = native_client
    env["TOPOLOGY_CALLS"] = str(path.parent / "topology-calls.jsonl")
    job = payload["jobs"][0]
    job.update(restart_cnt=0, nodes="compute-[a,b]", gres_detail=["gpu:example:2(IDX:1,3)"] * 2,
        job_resources={"nodes": {"count": 2, "list": "compute-[a,b]", "allocation": [
            {"name": name, "index": index, "cpus": {"count": 8}, "memory": {"allocated": 16384},
             "sockets": [{"index": socket, "cores": [{"index": core,
                "status": ["ALLOCATED"] if core in {1, 3} else ["UNALLOCATED"]} for core in range(4)]} for socket in range(2)]}
            for index, name in enumerate(["compute-a", "compute-b"])]}})
    path.write_text(json.dumps(payload))
    sinfo = {"meta": payload["meta"], "errors": [], "warnings": [], "sinfo": [
        {"nodes": {"nodes": [name]}, "sockets": {"minimum": 2, "maximum": 2},
         "cores": {"minimum": 4, "maximum": 4}, "threads": {"minimum": 2, "maximum": 2},
         "gres": {"total": "gpu:example:4"}} for name in ("compute-a", "compute-b")]}
    nodes = path.parent / "sinfo.json";nodes.write_text(json.dumps(sinfo));env["TOPOLOGY_NODES"] = str(nodes)
    for name in ("scontrol", "sinfo"):
        binary = path.parent / name
        binary.write_text(f"#!{sys.executable}\n" + '''
import json, os, sys
from pathlib import Path
with Path(os.environ['TOPOLOGY_CALLS']).open('a') as out:
    out.write(json.dumps({'argv':sys.argv,'uid':os.geteuid(),'secret':'SAI_TOKEN' in os.environ})+'\\n')
if sys.argv[1:3] == ['show','hostnames']:
    print('compute-a\\ncompute-b')
else:
    print(Path(os.environ['TOPOLOGY_NODES' if Path(sys.argv[0]).name == 'sinfo' else 'NATIVE_PAYLOAD']).read_text())
''')
        binary.chmod(0o755)
    return env, path, payload


def test_local_allocation_shares_native_projection_and_only_reads_allocated_nodes(topology_client, monkeypatch):
    env, path, raw = topology_client
    monkeypatch.setattr('sai_cli.config.resolve_settings', lambda *args: pytest.fail('local topology reached Portal'))
    code, text, error = invoke(env, 'jobs', 'local', '--job-id', '42')
    assert code == 0 and not error, error
    result = json.loads(text)
    from sai_native_slurm import normalize_job_allocation, bind_job_topology
    allocation = bind_job_topology(raw['jobs'][0], normalize_job_allocation(raw['jobs'][0]),
        ['compute-a','compute-b'], json.loads(Path(env['TOPOLOGY_NODES']).read_text()))
    assert result['allocation'] == {key:allocation[key] for key in ('status','nodes')}
    assert result['allocation']['nodes'][0]['cpu_ids'] == [2,3,6,7,10,11,14,15]
    assert result['allocation']['nodes'][0]['gres'][0]['indices'] == [1,3]
    calls=[json.loads(line) for line in Path(env['TOPOLOGY_CALLS']).read_text().splitlines()]
    assert len(calls)==3 and all(not call['secret'] for call in calls)
    assert calls[-1]['argv'][1:]==['--json','--local','--Node','--nodes=compute-a,compute-b']
    assert all(marker not in text for marker in ('private executable','PRIVATE=value','/private/work'))


def test_pending_array_zero_and_native_failure_do_not_invent_allocations(topology_client):
    env,path,payload=topology_client
    job=payload['jobs'][0]
    job.update(array_job_id={'set':True,'infinite':False,'number':40},array_task_id={'set':True,'infinite':False,'number':0}, job_state=['PENDING'])
    path.write_text(json.dumps(payload))
    code,text,error=invoke(env,'jobs','local','--job-id','40_0')
    assert code==0 and json.loads(text)['allocation']=={'status':'not_allocated','nodes':[]}
    assert len(Path(env['TOPOLOGY_CALLS']).read_text().splitlines())==1
    assert invoke(env,'jobs','local','--job-id','40')[0]==5
    assert invoke(env,'jobs','local','--job-id','40_0','-A','elsewhere')[0]==2
    job.update(array_task_id={'set':False,'infinite':False,'number':0}, array_task_string='0-3%2')
    path.write_text(json.dumps(payload))
    code,text,error=invoke(env,'jobs','local','--job-id','40_0')
    assert code==0,error
    assert json.loads(text)['job']['array_task_id']=='0'
    assert json.loads(text)['allocation']=={'status':'not_allocated','nodes':[]}
    assert invoke(env,'jobs','local','--job-id','40_8')[0]==5


def test_empty_exact_selector_never_falls_back_to_the_queue(topology_client):
    env,_,_=topology_client
    assert invoke(env,'jobs','local','--job-id','')[0]==2
    assert not Path(env['TOPOLOGY_CALLS']).exists() and not Path(env['NATIVE_CALL']).exists()


@pytest.mark.parametrize('width',[40,80,120])
def test_position_maps_keep_indices_and_cpu_ranges_at_terminal_width(topology_client,width):
    from sai_cli.allocation_view import render_allocation
    from rich.console import Console
    env,_,_=topology_client
    code,text,error=invoke(env,'jobs','local','--job-id','42')
    assert code==0,error
    rendered=render_allocation(json.loads(text),width=width)
    assert 'GPU  1, 3' in rendered
    assert '插槽 0' in rendered and '插槽 1' in rendered and '2–3' in rendered and '14–15' in rendered
    assert 'IDX' not in rendered and 'CPU S' not in rendered and '■' not in rendered
    assert max(Console().measure(line).maximum for line in rendered.splitlines())<=width


@pytest.mark.parametrize('gpu', [False, True])
@pytest.mark.parametrize('width', [40, 80, 120])
def test_two_dimensional_allocation_keeps_core_membership_and_monochrome_markers(topology_client, width, gpu):
    from sai_cli.allocation_view import render_allocation
    env, _, _ = topology_client
    code, raw, error = invoke(env, 'jobs', 'local', '--job-id', '42')
    assert code == 0, error
    value = json.loads(raw)
    value['allocation']['nodes'] = value['allocation']['nodes'][:1]
    node = value['allocation']['nodes'][0]
    if not gpu:
        node.update(gres=[], gpu_total=0)
    output = render_allocation(value, width=width, color=False)
    assert '\x1b' not in output
    assert all(f'核 {core}' in output for core in range(4))
    assert '* 2' in output or '*2' in output
    assert '*14' in output and '*15' in output
    socket_lines = [line for line in output.splitlines() if 'CPU 插槽' in line]
    assert len(socket_lines) == (2 if width == 40 else 1)
    if gpu:
        assert 'GPU  1, 3' in output and '* 1' in output and '* 3' in output
    else:
        assert 'GPU' not in output
