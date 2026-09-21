from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from _lua_runtime import run_lua


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "site" / "slurm" / "job_submit.lua"
RENDERER = ROOT / "scripts" / "render_job_submit_policy.py"


def _projection(*, generated_at: int = 1_785_823_200) -> dict:
    return {
        "schema_version": 3,
        "revision": "test-1",
        "generated_at": generated_at,
        "gpu_policy": {"per_node_multiple": 4, "exempt_qos": ["gpu-special"]},
    }


def _snapshot(tmp_path: Path, payload: dict | None = None) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    source = tmp_path / "projection.json"
    output = tmp_path / "job_submit_policy.lua"
    source.write_text(json.dumps(payload or _projection()), encoding="utf-8")
    subprocess.run(
        [sys.executable, str(RENDERER), "--input", str(source), "--output", str(output)],
        check=True,
        capture_output=True,
        text=True,
    )
    return output


def _prelude(snapshot: Path, *, expected: int = 0) -> str:
    return f"""
SAI_SUBMIT_POLICY_PATH = {json.dumps(str(snapshot))}
slurm = {{
    SUCCESS = 0,
    ERROR = -1,
    ESLURM_ACCOUNTING_POLICY = 2050,
    ESLURM_INVALID_GRES = 2070,
    NO_VAL16 = 65534,
}}
messages = {{}}
function slurm.user_msg(message) table.insert(messages, message) end
slurm.log_error = slurm.user_msg
assert(dofile({json.dumps(str(PLUGIN))}) == {expected})

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
assert(message_contains("WARNING: 请核对计费账户 / CHECK BILLING ACCOUNT"))
assert(message_contains("作业运行后，费用将记入 / Charges if run: Account=personal-alice"))
assert(message_contains("目录推导 / WorkDir account: Account=proj-research"))
assert(message_contains("Next submission: --account=<account>"))
assert(message_contains("Correct pending job: scontrol update JobId=<jobid> Account=<account>"))

messages = {}
local project = new_job({
    work_dir = "/org/org-example/proj-research/run",
    account = nil,
    tres_per_node = "gres/gpu:4",
})
assert(slurm_job_submit(project, {}, 1000) == slurm.SUCCESS)
assert(project.account == "proj-research")
assert(message_contains("Using WorkDir instead of default Account=personal-alice"))

for _, suffix in ipairs({"run 1", "计算/输入文件", "results (final)", "data[1]", "./计算", "input/../计算", "run//output/"}) do
    local named_directory = new_job({
        work_dir = "/org/org-example/proj-research/" .. suffix,
        default_account = "org-example",
        tres_per_node = "gres/gpu:4",
    })
    assert(slurm_job_submit(named_directory, {}, 1000) == slurm.SUCCESS)
    assert(named_directory.account == "proj-research")
    named_directory.work_dir = "/org/org-example/" .. suffix
    named_directory.account = nil
    assert(slurm_job_submit(named_directory, {}, 1000) == slurm.SUCCESS)
    assert(named_directory.account == "org-example")
end

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
assert(message_contains("Unresolved WorkDir"))
"""
    )


def test_submit_preserves_account_when_path_is_unresolved(tmp_path: Path) -> None:
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
assert(not message_contains("Unresolved WorkDir"))

messages = {}
local suspicious = new_job({
    work_dir = "/home/alice/workdir_org-example/../run", -- public-scan: allow-test-vector
    account = nil,
    tres_per_node = "gres/gpu:4",
})
assert(slurm_job_submit(suspicious, {}, 1000) == slurm.SUCCESS)
assert(suspicious.account == "private-alice")

local parent_account = new_job({work_dir = "/org//org-example/proj-research/../share/", tres_per_node = "gres/gpu:4"})
assert(slurm_job_submit(parent_account, {}, 1000) == slurm.SUCCESS)
assert(parent_account.account == "org-example")

messages = {}
local other_home = new_job({work_dir = "/home/bob/run", account = nil, tres_per_node = "gres/gpu:4"}) -- public-scan: allow-test-vector
assert(slurm_job_submit(other_home, {}, 1000) == slurm.SUCCESS)
assert(other_home.account == "personal-alice")
assert(message_contains("using Slurm default Account"))

messages = {}
local relative = new_job({work_dir = "relative/run", account = nil, default_account = "", tres_per_node = "gres/gpu:4"})
assert(slurm_job_submit(relative, {}, 1000) == slurm.ESLURM_ACCOUNTING_POLICY)
assert(message_contains("ERROR: SAI account policy: no explicit, path-derived, or the Slurm default account"))
"""
    )


def test_policy_is_versioned_configuration_and_invalid_load_is_rejected(tmp_path: Path) -> None:
    policy = _snapshot(tmp_path, _projection(generated_at=1))
    run_lua(
        _prelude(policy)
        + """
local exempt = new_job({tres_per_node = "gres/gpu:7", qos = "gpu-special"})
os.time = function() error("static site rules must not depend on a renewal timer") end
assert(slurm_job_submit(exempt, {}, 1000) == slurm.SUCCESS)
"""
    )

    run_lua(
        _prelude(tmp_path / "missing.lua", expected=-1)
        + 'assert(message_contains("missing or invalid"))'
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


def test_modify_validates_resulting_gpu_request_and_preserves_native_updates(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path)
    run_lua(
        _prelude(snapshot)
        + """
local gpu = {tres_per_node = "gres/gpu:4", qos = "normal", cpus_per_tres = "gpu:8", mem_per_tres = "gpu:4096"}
local odd = {tres_per_node = "gres/gpu:7", qos = "gpu-special"}
for _, current in ipairs({gpu, odd}) do
    for _, change in ipairs({{name = "renamed"}, {time_limit = 2}, {dependency = ""}, {account = "org-example"}}) do
        assert(slurm_job_modify(change, current, {}, 1000) == slurm.SUCCESS)
    end
end
assert(slurm_job_modify({qos = "normal"}, gpu, {}, 1000) == slurm.SUCCESS)
assert(slurm_job_modify({tres_per_node = "gres/gpu:8"}, gpu, {}, 1000) == slurm.SUCCESS)
assert(slurm_job_modify({tres_per_node = "gres/gpu:7", qos = "gpu-special"}, gpu, {}, 1000) == slurm.SUCCESS)
assert(slurm_job_modify({qos = "normal", tres_per_node = "gres/gpu:4"}, odd, {}, 1000) == slurm.SUCCESS)
assert(gpu.tres_per_node == "gres/gpu:4" and odd.qos == "gpu-special")

for _, change in ipairs({{qos = "normal"}, {tres_per_node = "gres/gpu:3", qos = "normal"}}) do
    messages = {}
    assert(slurm_job_modify(change, odd, {}, 1000) == slurm.ESLURM_INVALID_GRES)
    assert(message_contains("ERROR: SAI GPU policy: GPUs per node must be divisible by 4"))
end
for _, change in ipairs({{cpus_per_task = 2}, {min_mem_per_node = 1024}, {mem_per_tres = "gpu:1024"}}) do
    assert(slurm_job_modify(change, {}, {}, 1000) == slurm.SUCCESS)
    assert(slurm_job_modify(change, gpu, {}, 1000) == slurm.ESLURM_ACCOUNTING_POLICY)
end
assert(slurm_job_modify({tres_per_job = "gres/gpu:4"}, gpu, {}, 1000) == slurm.ESLURM_INVALID_GRES)
for _, change in ipairs({{tres_per_node = ""}, {tres_per_node = "gres/"}}) do
    assert(slurm_job_modify(change, gpu, {}, 1000) == slurm.ESLURM_INVALID_GRES)
end
assert(slurm_job_modify({tres_per_node = "gres/gpu:4"}, {min_mem_per_node = 2048}, {}, 1000) == slurm.ESLURM_INVALID_GRES)
assert(message_contains("resubmit to switch between CPU-only and GPU jobs"))
assert(slurm_job_modify({tres_per_node = "gres/gpu:3"}, gpu, {}, 0) == slurm.SUCCESS)
"""
    )


def test_modify_uses_submission_account_precedence_for_workdir_and_account(tmp_path: Path) -> None:
    run_lua(
        _prelude(_snapshot(tmp_path))
        + """
local current = {
    user_name = "alice",
    account = "personal-alice",
    work_dir = "/home/alice/run", -- public-scan: allow-test-vector
    tres_per_node = "gres/gpu:4",
    qos = "normal",
}

local workdir_only = {work_dir = "/org/org-example/proj-research/run"}
assert(slurm_job_modify(workdir_only, current, {}, 1000) == slurm.SUCCESS)
assert(workdir_only.account == "proj-research")
assert(message_contains("Charges if run: Account=proj-research"))
assert(message_contains("Correct pending job: scontrol update JobId=<jobid> Account=<account>"))
assert(not message_contains("Next submission:"))
assert(message_contains("WorkDir changes billing account: personal-alice -> proj-research"))

messages = {}
local explicit_only = {account = "proj-research"}
assert(slurm_job_modify(explicit_only, {
    user_name = "alice",
    account = "personal-alice",
    work_dir = "/home/alice/run", -- public-scan: allow-test-vector
    tres_per_node = "gres/gpu:4",
}, {}, 1000) == slurm.SUCCESS)
assert(explicit_only.account == "proj-research")
assert(message_contains("WorkDir account: Account=private-alice"))

messages = {}
local both = {
    work_dir = "/org/org-example/proj-research/run",
    account = "personal-alice",
}
assert(slurm_job_modify(both, current, {}, 1000) == slurm.SUCCESS)
assert(both.account == "personal-alice")
assert(message_contains("WorkDir account: Account=proj-research"))

messages = {}
local unresolved = {work_dir = "relative/run"}
assert(slurm_job_modify(unresolved, current, {}, 1000) == slurm.SUCCESS)
assert(unresolved.account == nil)
assert(message_contains("Charges if run: Account=personal-alice"))
assert(message_contains("Unresolved WorkDir; keeping existing job Account"))

-- Native array updates reuse the request across elements with different accounts.
current.account = "org-example"
assert(slurm_job_modify(unresolved, current, {}, 1000) == slurm.SUCCESS)
assert(unresolved.account == nil)
assert(message_contains("Charges if run: Account=org-example"))

-- A matching WorkDir must not add a needless Account update to a running job.
local matching = {work_dir = "/org/org-example/run"}
assert(slurm_job_modify(matching, current, {}, 1000) == slurm.SUCCESS)
assert(matching.account == nil)

messages = {}
local clear = {account = ""}
assert(slurm_job_modify(clear, current, {}, 1000) == slurm.SUCCESS)
assert(clear.account == "")
assert(#messages == 0)
clear.work_dir = "/org/org-example/proj-research"
assert(slurm_job_modify(clear, current, {}, 1000) == slurm.SUCCESS)
assert(clear.account == "")
assert(#messages == 0)

messages = {}
local unrelated = {name = "renamed"}
assert(slurm_job_modify(unrelated, current, {}, 1000) == slurm.SUCCESS)
assert(unrelated.account == nil)
assert(#messages == 0)

-- No default-account fallback on modification, and no revalidation of legacy GPUs.
assert(slurm_job_modify({work_dir = "/tmp", default_account = "org-example"}, {}, {}, 1000) == slurm.ESLURM_ACCOUNTING_POLICY)
current.tres_per_node = "gres/gpu:3"
assert(slurm_job_modify({account = "org-example"}, current, {}, 1000) == slurm.SUCCESS)
assert(slurm_job_modify({work_dir = "/tmp"}, current, {}, 1000) == slurm.SUCCESS)
"""
    )


def test_modify_qos_reset_uses_job_association_and_restores_unset_fields(tmp_path: Path) -> None:
    run_lua(
        _prelude(_snapshot(tmp_path))
        + """
local current = {account = "org-example", partition = "gpu-standard", qos = "gpu-special", tres_per_node = "gres/gpu:7"}
local fields = {qos = ""}
local change = setmetatable({}, {
    __index = function(_, key)
        if key == "default_qos" then
            assert(fields.account == "org-example" and fields.partition == "gpu-standard")
            return "normal"
        end
        return fields[key]
    end,
    __newindex = function(_, key, value)
        fields[key] = value ~= "" and value or nil
    end,
})
assert(slurm_job_modify(change, current, {}, 1000) == slurm.ESLURM_INVALID_GRES)
assert(fields.account == nil and fields.partition == nil and fields.qos == "")
current.tres_per_node = "gres/gpu:4"
assert(slurm_job_modify(change, current, {}, 1000) == slurm.SUCCESS)
assert(fields.account == nil and fields.partition == nil and fields.qos == "")

fields.work_dir = "/org/org-example/proj-research/run"
fields.user_name = "alice"
fields.tres_per_node = "gres/gpu:8"
setmetatable(change, {__index = function(_, key)
    if key == "default_qos" then
        assert(fields.account == "proj-research" and fields.partition == "gpu-standard")
        return "normal"
    end
    return fields[key]
end, __newindex = function(_, key, value)
    fields[key] = value ~= "" and value or nil
end})
assert(slurm_job_modify(change, current, {}, 1000) == slurm.SUCCESS)
assert(fields.account == "proj-research" and fields.partition == nil)
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
