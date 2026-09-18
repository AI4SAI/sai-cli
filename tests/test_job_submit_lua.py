from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from _lua_runtime import run_lua


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "site" / "slurm" / "job_submit.lua"
RENDERER = ROOT / "scripts" / "render_job_submit_snapshot.py"


def _projection(*, generated_at: int = 1_785_823_200, expires_at: int = 4_102_444_800) -> dict:
    return {
        "schema_version": 2,
        "revision": "test-1",
        "generated_at": generated_at,
        "expires_at": expires_at,
        "gpu_policy": {"per_node_multiple": 4, "exempt_qos": ["gpu-special"]},
    }


def _snapshot(tmp_path: Path, payload: dict | None = None) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    source = tmp_path / "projection.json"
    output = tmp_path / "account_snapshot.lua"
    source.write_text(json.dumps(payload or _projection()), encoding="utf-8")
    subprocess.run(
        [sys.executable, str(RENDERER), "--input", str(source), "--output", str(output)],
        check=True,
        capture_output=True,
        text=True,
    )
    return output


def _prelude(snapshot: Path) -> str:
    return f"""
SAI_ACCOUNT_SNAPSHOT_PATH = {json.dumps(str(snapshot))}
slurm = {{
    SUCCESS = 0,
    ERROR = -1,
    ESLURM_ACCOUNTING_POLICY = 2050,
    ESLURM_INVALID_GRES = 2070,
    NO_VAL16 = 65534,
}}
messages = {{}}
function slurm.user_msg(message) table.insert(messages, message) end
assert(dofile({json.dumps(str(PLUGIN))}) == slurm.SUCCESS)

function new_job(values)
    local job = {{
        user_name = "alice",
        work_dir = "/home/alice/run", -- public-scan: allow-test-vector
        default_account = "personal-alice",
        default_qos = "normal",
        cpus_per_task = slurm.NO_VAL16,
    }}
    for key, value in pairs(values or {{}}) do job[key] = value end
    return job
end

function message_contains(fragment)
    for _, message in ipairs(messages) do
        if string.find(message, fragment, 1, true) then return true end
    end
    return false
end
"""


def test_submit_applies_explicit_first_and_derives_canonical_paths(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path)
    run_lua(
        _prelude(snapshot)
        + """
local research = new_job({
    work_dir = "/org/org-example/proj-research/run",
    account = "personal-alice",
    tres_per_node = "gres/gpu:4",
})
assert(slurm_job_submit(research, {}, 1000) == slurm.SUCCESS)
assert(research.account == "personal-alice")
assert(message_contains("explicit account personal-alice differs from WorkDir account proj-research"))

messages = {}
local project = new_job({
    work_dir = "/org/org-example/proj-research/run",
    account = nil,
    tres_per_node = "gres/gpu:4",
})
assert(slurm_job_submit(project, {}, 1000) == slurm.SUCCESS)
assert(project.account == "proj-research")
assert(message_contains("differs from the Slurm default account personal-alice"))

messages = {}
local org = new_job({
    work_dir = "/org/org-example/share/run",
    account = nil,
    tres_per_node = "gres/gpu:4",
})
assert(slurm_job_submit(org, {}, 1000) == slurm.SUCCESS)
assert(org.account == "org-example")

messages = {}
local home = new_job({
    work_dir = "/home/alice/projects/run", -- public-scan: allow-test-vector
    account = nil,
    tres_per_node = "gres/gpu:4",
})
assert(slurm_job_submit(home, {}, 1000) == slurm.SUCCESS)
assert(home.account == "private-alice")

messages = {}
local alias = new_job({
    work_dir = "/home/alice/workdir_org-example/proj-research/run", -- public-scan: allow-test-vector
    account = nil,
    tres_per_node = "gres/gpu:4",
})
assert(slurm_job_submit(alias, {}, 1000) == slurm.SUCCESS)
assert(alias.account == "personal-alice")
assert(message_contains("WorkDir is unresolved"))
"""
    )


def test_submit_preserves_account_when_path_or_snapshot_is_unresolved(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path)
    run_lua(
        _prelude(snapshot)
        + """
local unknown = new_job({
    work_dir = "/org/org-example/unknown/run",
    account = nil,
    tres_per_node = "gres/gpu:4",
})
assert(slurm_job_submit(unknown, {}, 1000) == slurm.SUCCESS)
assert(unknown.account == "org-example")
assert(not message_contains("WorkDir is unresolved"))

messages = {}
local suspicious = new_job({
    work_dir = "/home/alice/workdir_org-example/../run", -- public-scan: allow-test-vector
    account = nil,
    tres_per_node = "gres/gpu:4",
})
assert(slurm_job_submit(suspicious, {}, 1000) == slurm.SUCCESS)
assert(suspicious.account == "personal-alice")
assert(message_contains("WorkDir is unresolved"))

messages = {}
local other_home = new_job({work_dir = "/home/bob/run", account = nil, tres_per_node = "gres/gpu:4"}) -- public-scan: allow-test-vector
assert(slurm_job_submit(other_home, {}, 1000) == slurm.SUCCESS)
assert(other_home.account == "personal-alice")
assert(message_contains("keeping the Slurm default account"))

messages = {}
local relative = new_job({work_dir = "relative/run", account = nil, default_account = "", tres_per_node = "gres/gpu:4"})
assert(slurm_job_submit(relative, {}, 1000) == slurm.ESLURM_ACCOUNTING_POLICY)
assert(message_contains("no explicit, path-derived, or Slurm default account"))
"""
    )

    stale = _snapshot(tmp_path / "stale", _projection(generated_at=1, expires_at=2))
    run_lua(
        _prelude(stale)
        + """
local job = new_job({account = nil, tres_per_node = "gres/gpu:4"})
assert(slurm_job_submit(job, {}, 1000) == slurm.SUCCESS)
assert(job.account == "private-alice")
local exempt = new_job({tres_per_node = "gres/gpu:7", qos = "gpu-special"})
assert(slurm_job_submit(exempt, {}, 1000) == slurm.ESLURM_INVALID_GRES)
"""
    )

    run_lua(
        _prelude(snapshot)
        + """
local now = 2000000000
os.time = function() return now end
local exempt = new_job({tres_per_node = "gres/gpu:7", qos = "gpu-special"})
assert(slurm_job_submit(exempt, {}, 1000) == slurm.SUCCESS)
now = 4102444800
assert(slurm_job_submit(exempt, {}, 1000) == slurm.ESLURM_INVALID_GRES)
"""
    )

    run_lua(
        _prelude(tmp_path / "missing.lua")
        + """
local job = new_job({account = nil, tres_per_node = "gres/gpu:4"})
assert(slurm_job_submit(job, {}, 1000) == slurm.SUCCESS)
assert(job.account == "private-alice")
"""
    )


def test_submit_rejects_explicit_cpu_and_memory_overrides_on_gpu_jobs(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path)
    run_lua(
        _prelude(snapshot)
        + """
local cases = {
    {values = {cpus_per_task = 2}, message = "--cpus-per-task"},
    {values = {cpus_per_tres = "gres/gpu:2"}, message = "--cpus-per-gpu"},
    {values = {min_mem_per_node = 4096}, message = "--mem"},
    {values = {min_mem_per_cpu = 1024}, message = "--mem-per-cpu"},
    {values = {mem_per_tres = "gres/gpu:8192"}, message = "--mem-per-gpu"},
}
for _, case in ipairs(cases) do
    messages = {}
    case.values.tres_per_node = "gres/gpu:4"
    local job = new_job(case.values)
    assert(slurm_job_submit(job, {}, 1000) == slurm.ESLURM_ACCOUNTING_POLICY)
    assert(message_contains(case.message))
end

local cpu_job = new_job({cpus_per_task = 2})
assert(slurm_job_submit(cpu_job, {}, 1000) == slurm.SUCCESS)
"""
    )


def test_submit_enforces_per_node_gpu_shape_and_effective_qos(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path)
    run_lua(
        _prelude(snapshot)
        + """
local odd = new_job({tres_per_node = "gres/gpu:7"})
assert(slurm_job_submit(odd, {}, 1000) == slurm.ESLURM_INVALID_GRES)
assert(message_contains("divisible by 4"))

messages = {}
local exempt = new_job({tres_per_node = "gres/gpu:7", qos = "gpu-special"})
assert(slurm_job_submit(exempt, {}, 1000) == slurm.SUCCESS)

local default_exempt = new_job({tres_per_node = "gres/gpu:7", default_qos = "gpu-special"})
assert(slurm_job_submit(default_exempt, {}, 1000) == slurm.SUCCESS)

local typed = new_job({tres_per_node = "gres/gpu:v100:4"})
assert(slurm_job_submit(typed, {}, 1000) == slurm.SUCCESS)

messages = {}
local per_job = new_job({tres_per_job = "gres/gpu:4"})
assert(slurm_job_submit(per_job, {}, 1000) == slurm.ESLURM_INVALID_GRES)
assert(message_contains("--gpus-per-node"))
"""
    )


def test_modify_blocks_policy_owned_fields_for_non_root(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path)
    run_lua(
        _prelude(snapshot)
        + """
local harmless = new_job({name = "renamed"})
assert(slurm_job_modify(harmless, {}, {}, 1000) == slurm.SUCCESS)

messages = {}
local account_change = new_job({account = "org-example"})
assert(slurm_job_modify(account_change, {}, {}, 1000) == slurm.ESLURM_ACCOUNTING_POLICY)
assert(message_contains("cannot be changed after submission"))
assert(slurm_job_modify(account_change, {}, {}, 0) == slurm.SUCCESS)
"""
    )


def test_submit_callback_has_no_runtime_external_io() -> None:
    text = PLUGIN.read_text(encoding="utf-8")
    submit_body = text.split("function slurm_job_submit", 1)[1]

    assert text.count("dofile") == 1
    assert "dofile" not in submit_body
    assert "require(" not in text
    assert "io." not in text
    assert "os.execute" not in text
    assert "popen" not in text
    assert "package.loadlib" not in text
