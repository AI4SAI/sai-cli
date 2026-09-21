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

local function work_dir_components(path)
    if not nonempty(path) or #path > 4096 or string.sub(path, 1, 1) ~= "/" then
        return nil
    end
    local components = {}
    for component in string.gmatch(path, "[^/]+") do
        if component == ".." then
            table.remove(components)
        elseif component ~= "." then
            table.insert(components, component)
        end
    end
    return components
end

local function canonical_path_token(value)
    return nonempty(value)
        and #value <= 64
        and string.match(value, "^[a-z][a-z0-9_-]*$") ~= nil
end

local function inferred_account(work_dir, username)
    local components = work_dir_components(work_dir)
    if not components or not nonempty(username) then return nil end

    local root, owner, child = components[1], components[2], components[3]
    if not canonical_path_token(root) or not canonical_path_token(owner) then return nil end
    if root == "org" then
        if canonical_path_token(child) and string.sub(child, 1, 5) == "proj-" then
            return child
        end
        return owner
    end
    if root ~= "home" or owner ~= username then return nil end

    if nonempty(child) and string.sub(child, 1, 8) == "workdir_" then
        return nil
    end
    return "private-" .. username
end

local function warn_billing_account(account, reason, modifying)
    local action = ""
    if not modifying then
        action = "\n后续提交 / Next submission: --account=<account>"
    end
    slurm.user_msg("WARNING: 请核对计费账户 / CHECK BILLING ACCOUNT\n"
        .. "作业运行后，费用将记入 / Charges if run: Account=" .. account .. "\n"
        .. reason .. action
        .. "\n排队作业更正 / Correct pending job: scontrol update JobId=<jobid> Account=<account>")
end

local function apply_account_policy(job_desc, job_ptr)
    if job_ptr and (job_desc.account == ""
        or (job_desc.work_dir == nil and job_desc.account == nil)) then
        return true
    end

    local work_dir, username = job_desc.work_dir, job_desc.user_name
    local fallback, label
    if job_ptr then
        work_dir = work_dir or job_ptr.work_dir
        username = job_ptr.user_name or username
        fallback, label = job_ptr.account, "existing job account "
    else
        fallback, label = job_desc.default_account, "the Slurm default account "
    end
    local inferred = inferred_account(work_dir, username)
    local explicit = nonempty(job_desc.account) and job_desc.account or nil
    if explicit then
        if inferred and explicit ~= inferred then
            warn_billing_account(explicit, "目录推导 / WorkDir account: Account=" .. inferred
                .. "；本次显式指定优先 / explicit account takes precedence.", job_ptr)
        elseif not inferred then
            warn_billing_account(explicit,
                "目录无法推导账户，使用本次显式指定 / Unresolved WorkDir; using explicit Account.", job_ptr)
        end
        return true
    end
    if not nonempty(inferred) then
        if nonempty(fallback) then
            -- Slurm reuses array update requests; leave each job's account untouched.
            if not job_ptr then job_desc.account = fallback end
            local reason = job_ptr
                and "目录无法推导账户，保留作业原账户 / Unresolved WorkDir; keeping existing job Account."
                or "目录无法推导账户，使用默认账户 / Unresolved WorkDir; using Slurm default Account."
            warn_billing_account(fallback, reason, job_ptr)
            return true
        end
        slurm.user_msg("ERROR: SAI account policy: no explicit, path-derived, or " .. label .. "is available.")
        return false
    end
    if not job_ptr or inferred ~= job_ptr.account then job_desc.account = inferred end
    if nonempty(fallback) and fallback ~= inferred then
        local reason = job_ptr
            and "按新目录切换账户 / WorkDir changes billing account: " .. fallback .. " -> " .. inferred
            or "按目录选择，未使用默认账户 / Using WorkDir instead of default Account=" .. fallback
        warn_billing_account(inferred, reason, job_ptr)
    end
    return true
end

local function resource_override_error(job_desc)
    if specified_number(job_desc.cpus_per_task, slurm.NO_VAL16) then
        return "ERROR: SAI GPU policy: CPUs follow GPU count; omit --cpus-per-task / CPUsPerTask."
    end
    if nonempty(job_desc.cpus_per_tres) then
        return "ERROR: SAI GPU policy: CPUs follow GPU count; omit --cpus-per-gpu / CpusPerTres."
    end
    if job_desc.min_mem_per_node ~= nil then
        return "ERROR: SAI GPU policy: memory follows GPU count; omit --mem / MinMemoryNode."
    end
    if job_desc.min_mem_per_cpu ~= nil then
        return "ERROR: SAI GPU policy: memory follows GPU count; omit --mem-per-cpu / MinMemoryCPU."
    end
    if nonempty(job_desc.mem_per_tres) then
        return "ERROR: SAI GPU policy: memory follows GPU count; omit --mem-per-gpu / MemPerTres."
    end
    return nil
end

local function validate_gpu_policy(job_desc, overrides)
    local has_gpu, gpu_count, invalid_gpu_shape = gpu_request(job_desc)
    if not has_gpu then return slurm.SUCCESS end

    local override_error = resource_override_error(overrides)
    if override_error then
        slurm.user_msg(override_error)
        return policy_error
    end
    if invalid_gpu_shape or not gpu_count then
        slurm.user_msg("ERROR: SAI GPU policy: request GPUs per node with --gpus-per-node / Gres=gpu:N.")
        return gres_error
    end

    local qos = nonempty(job_desc.qos) and job_desc.qos or job_desc.default_qos
    if not exempt_qos[qos] and gpu_count % gpu_multiple ~= 0 then
        slurm.user_msg("ERROR: SAI GPU policy: GPUs per node must be divisible by " .. gpu_multiple
            .. " for QOS " .. (qos or "(default)") .. "; requested " .. gpu_count
            .. ". Change the GPU count or select a permitted QOS for this count.")
        return gres_error
    end
    return slurm.SUCCESS
end

function slurm_job_submit(job_desc, part_list, submit_uid)
    if not apply_account_policy(job_desc) then return policy_error end
    return validate_gpu_policy(job_desc, job_desc)
end

local function updated_qos(job_desc, job_ptr)
    if job_desc.qos == nil then return job_ptr.qos end
    if job_desc.qos ~= "" then return job_desc.qos end
    -- QOS= resets the default for this job's association, not the user's default account.
    local account, partition = job_desc.account, job_desc.partition
    if account == nil then job_desc.account = job_ptr.account end
    if partition == nil then job_desc.partition = job_ptr.partition end
    local qos = job_desc.default_qos
    -- The native Lua setters use an empty string to restore an unset field.
    if account == nil then job_desc.account = "" end
    if partition == nil then job_desc.partition = "" end
    return qos
end

function slurm_job_modify(job_desc, job_ptr, part_list, modify_uid)
    if modify_uid == 0 then return slurm.SUCCESS end
    if not apply_account_policy(job_desc, job_ptr) then return policy_error end
    local effective = {}
    local changed = job_desc.qos ~= nil or resource_override_error(job_desc) ~= nil
    for _, field in ipairs({"tres_per_job", "tres_per_node", "tres_per_socket", "tres_per_task"}) do
        effective[field] = job_desc[field] or job_ptr[field]
        changed = changed or job_desc[field] ~= nil
    end
    if not changed then return slurm.SUCCESS end
    local had_gpu = gpu_request(job_ptr) or contains_gpu(job_ptr.gres_req)
    if gpu_request(effective) ~= had_gpu then
        slurm.user_msg("ERROR: SAI GPU policy: resubmit to switch between CPU-only and GPU jobs; native updates retain the old resource settings.")
        return gres_error
    end
    effective.qos = updated_qos(job_desc, job_ptr)
    return validate_gpu_policy(effective, job_desc)
end

return slurm.SUCCESS
