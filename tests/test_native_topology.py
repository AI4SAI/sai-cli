"""Real native subprocesses share the installed gateway parser, without OAuth."""
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest
from test_local_jobs import native_client, native_job, invoke


def test_shared_reader_does_not_export_operator_capture_builders():
    import sai_native_topology as topology
    assert callable(topology.normalize_join) and callable(topology.job_cpu_locality)
    assert not hasattr(topology, 'build_interconnect')
    assert not hasattr(topology, 'parse_nvidia_topology')


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
    assert 'CPU  2–3, 6–7, 10–11, 14–15' in rendered
    assert '硬件互联未记录' in rendered
    assert 'CPU 插槽' not in rendered and '核 0' not in rendered
    assert max(Console().measure(line).maximum for line in rendered.splitlines())<=width


@pytest.mark.parametrize('gpu', [False, True])
@pytest.mark.parametrize('width', [40, 80, 120])
def test_allocation_default_is_compact_and_keeps_unknown_topology_explicit(topology_client, width, gpu):
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
    assert 'CPU 插槽' not in output
    assert '硬件互联未记录' in output
    assert ('GPU  1, 3' in output) is gpu


def test_compact_view_does_not_expand_for_three_digit_ids(topology_client):
    from sai_cli.allocation_view import render_allocation
    code, raw, error = invoke(topology_client[0], 'jobs', 'local', '--job-id', '42')
    assert code == 0, error
    value = json.loads(raw)
    node = value['allocation']['nodes'][0]
    node.update(cpu_ids=list(range(32,48)), cpu_topology={'sockets':4,'cores_per_socket':16,'threads_per_core':2})
    value['allocation']['nodes'] = [node]
    output = render_allocation(value, width=80)
    assert 'CPU  32–47' in output
    assert 'CPU 插槽' not in output


def test_interconnect_view_shows_cpu_gpu_gpu_gpu_and_node_edges(topology_client):
    from rich.console import Console
    from sai_cli.allocation_view import render_allocation
    env, _, _ = topology_client
    code, raw, error = invoke(env, 'jobs', 'local', '--job-id', '42')
    assert code == 0, error
    value = json.loads(raw)
    value['allocation']['nodes'] = value['allocation']['nodes'][:1]
    record = {
        'schema_version': 'node.interconnect/v1', 'node': 'compute-a', 'cluster': 'cluster-a',
        'boot_time': 1767210000, 'slurmd_start_time': 1767211000, 'observed_at': '2026-01-01T00:00:00Z', 'expires_at': '2027-01-01T00:00:00Z',
        'cpu_topology': {'sockets': 2, 'cores_per_socket': 4, 'threads_per_core': 2},
        'numa': [{'id': 0, 'packages': [0], 'linux_cpu_ids': list(range(8))}],
        'gpus': [{'index': 0, 'numa': 0, 'cpu_ids': list(range(8))},
                 {'index': 1, 'numa': 0, 'cpu_ids': list(range(8))}],
        'links': [{'a': 0, 'b': 1, 'kind': 'NV2'}],
        'nics': [{'index': 0, 'gpu_paths': [{'gpu': 0, 'kind': 'PIX'}],
                  'peer': 'endpoint-0123456789abcdef01234567', 'rate_gbps': 100}],
    }
    value['interconnect'] = {'nodes':[{'node':'compute-a','status':'recorded','value':record}]}
    value['allocation']['nodes'][0]['gres'][0]['indices'] = [0, 1]
    output = render_allocation(value, width=80, color=False)
    assert 'NVLink ×2' in output
    assert 'NUMA 0' in output and '0*' in output and '1*' in output
    from sai_cli.interconnect_view import fabric_view
    from io import StringIO
    stream = StringIO()
    Console(file=stream).print(fabric_view(value['allocation']['nodes'], {'compute-a':record}, chinese=True))
    assert 'NIC 0' in stream.getvalue() and '连接点 1' in stream.getvalue()
    assert '01234567' not in stream.getvalue()
    assert 'CPU 插槽' not in output
    assert max(Console().measure(line).maximum for line in output.splitlines()) <= 80


def test_multi_node_fabric_keeps_only_observed_connection_without_hash_labels():
    from sai_cli.interconnect_view import fabric_view
    from rich.console import Console
    from io import StringIO
    peers=['endpoint-'+'a'*24,'endpoint-'+'b'*24]
    nodes=[{'name':'compute-a'},{'name':'compute-b'}]
    records={node['name']:{'nics':[{'index':0,'peer':peer,'rate_gbps':100}],
              'fabric_links':[{'a':peers[0],'b':peers[1],'kind':'infiniband'}]} for node,peer in zip(nodes,peers)}
    out=StringIO();Console(file=out,width=40).print(fabric_view(nodes,records,chinese=True))
    text=out.getvalue()
    assert 'compute-a' in text and 'compute-b' in text and '── IB ──' in text
    assert 'endpoint-' not in text and '交换机' not in text


def test_sparse_nvlink_cycle_is_not_drawn_as_all_to_all():
    from sai_cli.interconnect_view import nvlink_summary
    from rich.console import Console
    from io import StringIO
    value={'links':[{'a':a,'b':b,'kind':'NV2'} for a,b in [(0,1),(1,2),(2,3),(0,3)]]}
    out=StringIO();Console(file=out,width=80).print(nvlink_summary(value,{0,1,2,3},chinese=True))
    text=out.getvalue()
    assert '全互联' not in text and 'GPU 0 ─ NV2 ─ GPU 2' not in text
    value['links'] += [{'a':0,'b':2,'kind':'NV2'},{'a':1,'b':3,'kind':'NV2'}]
    out=StringIO();Console(file=out,width=80).print(nvlink_summary(value,{0,1,2,3},chinese=True))
    assert 'NVLink ×2 全互联' in out.getvalue()


def test_cpu_locality_view_uses_native_mapping_across_numa_and_stays_compact():
    from io import StringIO
    from rich.console import Console
    from sai_cli.interconnect_view import node_interconnect
    value = {'numa': [
        {'id': 0, 'packages': [0], 'linux_cpu_ids': [0, 1, 2, 3]},
        {'id': 1, 'packages': [1], 'linux_cpu_ids': [4, 5, 6, 7]}],
        'gpus': [], 'links': [], 'observed_at': '2026-01-01T00:00:00Z',
        'cpu_mapping': {'observed_at': '2026-01-01T00:00:00Z', 'slurm_to_linux': [0, 4, 1, 5, 2, 6, 3, 7]}}
    for width in (40, 100):
        out = StringIO()
        Console(file=out, width=width).print(node_interconnect(value, occupied=set(), cpu_ids=[0, 1], chinese=True, width=width))
        text = out.getvalue()
        assert 'NUMA 0 · 1/4 CPU*' in text and 'NUMA 1 · 1/4 CPU*' in text
        assert 'Linux CPU' not in text and len(text.splitlines()) < 10
    del value['cpu_mapping']
    out = StringIO()
    Console(file=out, width=40).print(node_interconnect(value, occupied=set(), cpu_ids=[0, 1], chinese=True, width=40))
    assert 'CPU*' not in out.getvalue() and 'CPU 落点未记录' in out.getvalue()


def test_interconnect_layout_handles_sparse_domains_and_partial_gpu_groups():
    from io import StringIO
    from rich.console import Console
    from sai_cli.interconnect_view import node_interconnect, nvlink_summary
    value = {'numa': [
        {'id': 7, 'packages': [12], 'linux_cpu_ids': [0, 32]},
        {'id': 21, 'packages': [12], 'linux_cpu_ids': [2, 34]},
        {'id': 99, 'packages': [40], 'linux_cpu_ids': [8, 40]}],
        'gpus': [], 'links': [], 'cpu_mapping': {'slurm_to_linux': [0, 32, 2, 34, 8, 40]}}
    out = StringIO()
    Console(file=out, width=40).print(node_interconnect(value, occupied=set(), cpu_ids=[1, 4], chinese=True, width=40))
    assert 'NUMA 7 · 1/2 CPU*' in out.getvalue() and 'NUMA 99 · 1/2 CPU*' in out.getvalue()
    assert 'CPU 12' in out.getvalue() and 'CPU 40' in out.getvalue()
    value = {'links': [{'a': a, 'b': b, 'kind': 'NV2'} for a, b in [(0, 1), (0, 2), (1, 2)]]}
    out = StringIO()
    Console(file=out, width=40).print(nvlink_summary(value, {0, 2}, chinese=True))
    assert 'GPU 0, 2' in out.getvalue() and '0–2' not in out.getvalue()


@pytest.mark.parametrize('width', [40, 100])
def test_gpu_connection_matrix_explains_only_displayed_paths(width):
    from itertools import combinations
    from io import StringIO
    from rich.console import Console
    from sai_cli.interconnect_view import node_interconnect
    indices = [0, 2, 5, 7]
    value = {'numa': [{'id': 0, 'packages': [0], 'linux_cpu_ids': [0, 1]}],
             'gpus': [{'index': index, 'numa': 0, 'cpu_ids': [0, 1]} for index in indices],
             'links': [{'a': a, 'b': b, 'kind': kind} for (a, b), kind in zip(
                 combinations(indices, 2), ['PIX', 'PXB', 'PHB', 'NODE', 'SYS', 'NV2'])]}
    output = StringIO()
    Console(file=output, width=width).print(node_interconnect(value, occupied=set(indices), chinese=True, width=width))
    text = output.getvalue()
    for explanation in ['PIX：单级 PCIe', 'PXB：多级 PCIe', 'PHB：经 CPU 桥', 'NODE：同 NUMA', 'SYS：跨 NUMA', 'NV#：NVLink 条数']:
        assert explanation in text.replace('\n', ' ')
    output = StringIO()
    Console(file=output, width=width).print(node_interconnect(value, occupied={0, 2, 5}, chinese=True, width=width))
    text = output.getvalue()
    assert 'NV#' not in text and 'SYS：' not in text and 'PHB：' not in text
