local snapshot_path = rawget(_G, "SAI_SUBMIT_POLICY_PATH")
    or "/etc/slurm/sai/job_submit_policy.lua"
local loaded, snapshot = pcall(dofile, snapshot_path)

local snapshot_ready = loaded
    and type(snapshot) == "table"
    and snapshot.schema_version == 3
    and type(snapshot.revision) == "string"
    and type(snapshot.gpu_multiple_exempt_qos) == "table"
    and type(snapshot.gpu_per_node_multiple) == "number"
    and snapshot.gpu_per_node_multiple >= 1
    and snapshot.gpu_per_node_multiple % 1 == 0
if not snapshot_ready then
    slurm.log_error("SAI submit policy is missing or invalid; refusing this Lua revision.")
    return slurm.ERROR
end
local exempt_qos = snapshot.gpu_multiple_exempt_qos
local gpu_multiple = snapshot.gpu_per_node_multiple

local policy_error = slurm.ESLURM_ACCOUNTING_POLICY or slurm.ERROR
local gres_error = slurm.ESLURM_INVALID_GRES or policy_error

local function nonempty(value)
    return type(value) == "string" and value ~= ""
end

local function specified_number(value, unset)
    return type(value) == "number" and value ~= unset
end

local function contains_gpu(value)
    return nonempty(value) and string.find(value, "gpu", 1, true) ~= nil
end

local function gpu_count_per_node(value)
    if not nonempty(value) then return nil, false end
    local total, found = 0, false
    for token in string.gmatch(value, "[^,]+") do
        if contains_gpu(token) then
            local count = string.match(token, "^gres/gpu:(%d+)$")
                or string.match(token, "^gres/gpu:[%w_.-]+:(%d+)$")
                or string.match(token, "^gpu:(%d+)$")
                or string.match(token, "^gpu:[%w_.-]+:(%d+)$")
            if not count then return nil, true end
            total, found = total + tonumber(count), true
        end
    end
    if not found or total < 1 then return nil, found end
    return total, false
end

local function gpu_request(job_desc)
    local count, invalid = gpu_count_per_node(job_desc.tres_per_node)
    local off_node = contains_gpu(job_desc.tres_per_job)
        or contains_gpu(job_desc.tres_per_socket)
        or contains_gpu(job_desc.tres_per_task)
    return count ~= nil or invalid or off_node, count, invalid or off_node
end

local function canonical_work_dir(path)
    if not nonempty(path) or #path > 4096 or string.sub(path, 1, 1) ~= "/" then
        return false
    end
    local guarded = path .. "/"
    if string.find(path, "//", 1, true)
        or string.find(guarded, "/./", 1, true)
        or string.find(guarded, "/../", 1, true) then
        return false
    end
    for component in string.gmatch(path, "[^/]+") do
        if string.match(component, "^[A-Za-z0-9_.-]+$") == nil then
            return false
        end
    end
    return true
end

local function canonical_path_token(value)
    return nonempty(value)
        and #value <= 64
        and string.match(value, "^[a-z][a-z0-9_-]*$") ~= nil
end

local function inferred_account(job_desc)
    local path, username = job_desc.work_dir, job_desc.user_name
    if not canonical_work_dir(path) or not nonempty(username) then return nil end

    local root, owner, rest = string.match(path, "^/([^/]+)/([^/]+)(.*)$")
    if not canonical_path_token(root) or not canonical_path_token(owner) then return nil end
    if root == "org" then
        local child = rest and string.match(rest, "^/([^/]+)") or nil
        if nonempty(child) and not canonical_path_token(child) then return nil end
        if nonempty(child) and string.sub(child, 1, 5) == "proj-" then
            return child
        end
        return owner
    end
    if root ~= "home" or owner ~= username then return nil end

    local child = rest and string.match(rest, "^/([^/]+)") or nil
    if nonempty(child) and string.sub(child, 1, 8) == "workdir_" then
        return nil
    end
    return "private-" .. username
end

local function apply_work_dir_account(job_desc)
    local inferred = inferred_account(job_desc)
    local explicit = nonempty(job_desc.account) and job_desc.account or nil
    local default_account = nonempty(job_desc.default_account) and job_desc.default_account or nil
    if explicit then
        if inferred and explicit ~= inferred then
            slurm.user_msg("SAI account policy: explicit account " .. explicit
                .. " differs from WorkDir account " .. inferred .. "; keeping explicit account.")
        elseif not inferred then
            slurm.user_msg("SAI account policy: WorkDir is unresolved; keeping the explicit account.")
        end
        return true
    end
    if not nonempty(inferred) then
        if default_account then
            job_desc.account = default_account
            slurm.user_msg("SAI account policy: WorkDir is unresolved; keeping the Slurm default account.")
            return true
        end
        slurm.user_msg("SAI account policy: no explicit, path-derived, or Slurm default account is available.")
        return false
    end
    job_desc.account = inferred
    if default_account and default_account ~= inferred then
        slurm.user_msg("SAI account policy: WorkDir account " .. inferred
            .. " differs from the Slurm default account " .. default_account .. "; using WorkDir account.")
    end
    return true
end

local function resource_override_error(job_desc)
    if specified_number(job_desc.cpus_per_task, slurm.NO_VAL16) then
        return "SAI GPU policy: --cpus-per-task is not allowed."
    end
    if nonempty(job_desc.cpus_per_tres) then
        return "SAI GPU policy: --cpus-per-gpu is not allowed."
    end
    if job_desc.min_mem_per_node ~= nil then
        return "SAI GPU policy: --mem is not allowed."
    end
    if job_desc.min_mem_per_cpu ~= nil then
        return "SAI GPU policy: --mem-per-cpu is not allowed."
    end
    if nonempty(job_desc.mem_per_tres) then
        return "SAI GPU policy: --mem-per-gpu is not allowed."
    end
    return nil
end

function slurm_job_submit(job_desc, part_list, submit_uid)
    if not apply_work_dir_account(job_desc) then return policy_error end

    local has_gpu, gpu_count, invalid_gpu_shape = gpu_request(job_desc)
    if not has_gpu then return slurm.SUCCESS end

    local override_error = resource_override_error(job_desc)
    if override_error then
        slurm.user_msg(override_error)
        return policy_error
    end
    if invalid_gpu_shape or not gpu_count then
        slurm.user_msg("SAI GPU policy: request GPUs with --gpus-per-node.")
        return gres_error
    end

    local qos = nonempty(job_desc.qos) and job_desc.qos or job_desc.default_qos
    if not exempt_qos[qos] and gpu_count % gpu_multiple ~= 0 then
        slurm.user_msg("SAI GPU policy: GPUs per node must be divisible by " .. gpu_multiple .. ".")
        return gres_error
    end
    return slurm.SUCCESS
end

local function changes_policy_field(job_desc)
    return nonempty(job_desc.account)
        or nonempty(job_desc.qos)
        or specified_number(job_desc.cpus_per_task, slurm.NO_VAL16)
        or nonempty(job_desc.cpus_per_tres)
        or job_desc.min_mem_per_node ~= nil
        or job_desc.min_mem_per_cpu ~= nil
        or nonempty(job_desc.mem_per_tres)
        or nonempty(job_desc.tres_per_job)
        or nonempty(job_desc.tres_per_node)
        or nonempty(job_desc.tres_per_socket)
        or nonempty(job_desc.tres_per_task)
end

function slurm_job_modify(job_desc, job_ptr, part_list, modify_uid)
    if modify_uid ~= 0 and changes_policy_field(job_desc) then
        slurm.user_msg("SAI policy: account, QOS, CPU, memory, and GPU shape cannot be changed after submission.")
        return policy_error
    end
    return slurm.SUCCESS
end

return slurm.SUCCESS
