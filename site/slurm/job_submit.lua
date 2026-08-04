local snapshot_path = rawget(_G, "SAI_ACCOUNT_SNAPSHOT_PATH")
    or "/etc/slurm/sai/account_snapshot.lua"
local loaded, snapshot = pcall(dofile, snapshot_path)

local snapshot_ready = loaded
    and type(snapshot) == "table"
    and snapshot.schema_version == 1
    and type(snapshot.expires_at) == "number"
local personal_accounts = snapshot_ready and snapshot.personal_accounts or {}
local org_accounts = snapshot_ready and snapshot.org_accounts or {}
local project_accounts = snapshot_ready and snapshot.project_accounts or {}
local home_aliases = snapshot_ready and snapshot.home_aliases or {}
local exempt_qos = snapshot_ready and snapshot.gpu_multiple_exempt_qos or {}
local gpu_multiple = snapshot_ready and snapshot.gpu_per_node_multiple or 4

if type(personal_accounts) ~= "table" then personal_accounts = {} end
if type(org_accounts) ~= "table" then org_accounts = {} end
if type(project_accounts) ~= "table" then project_accounts = {} end
if type(home_aliases) ~= "table" then home_aliases = {} end
if type(exempt_qos) ~= "table" then exempt_qos = {} end
if type(gpu_multiple) ~= "number" or gpu_multiple < 1 or gpu_multiple % 1 ~= 0 then
    gpu_multiple = 4
end

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
    return not string.find(path, "//", 1, true)
        and not string.find(guarded, "/./", 1, true)
        and not string.find(guarded, "/../", 1, true)
end

local function account_for_org(org, project)
    local org_account = org_accounts[org]
    if not nonempty(org_account) then return nil end
    if project then
        local project_account = project_accounts[org .. "/" .. project]
        if nonempty(project_account) then return project_account end
        if string.sub(project, 1, 5) == "proj-" then return nil end
    end
    return org_account
end

local function inferred_account(job_desc)
    if not snapshot_ready or os.time() >= snapshot.expires_at then return nil end
    local path, username = job_desc.work_dir, job_desc.user_name
    if not canonical_work_dir(path) or not nonempty(username) then return nil end

    local root, owner, rest = string.match(path, "^/([^/]+)/([^/]+)(.*)$")
    if root == "org" then
        local project = rest and string.match(rest, "^/([^/]+)") or nil
        return account_for_org(owner, project)
    end
    if root ~= "home" or owner ~= username then return nil end

    local alias, tail = string.match(rest or "", "^/([^/]+)(.*)$")
    if not alias then return personal_accounts[username] end
    if string.sub(alias, 1, 8) ~= "workdir_" then
        return personal_accounts[username]
    end

    local org = home_aliases[username .. "/" .. alias]
    if not nonempty(org) then return nil end
    local project = tail and string.match(tail, "^/([^/]+)") or nil
    return account_for_org(org, project)
end

local function apply_work_dir_account(job_desc)
    local inferred = inferred_account(job_desc)
    if not nonempty(inferred) then
        slurm.user_msg("SAI account policy: WorkDir is unresolved; keeping the requested/default account.")
        return
    end
    local current = nonempty(job_desc.account) and job_desc.account or job_desc.default_account
    if current ~= inferred then
        job_desc.account = inferred
        slurm.user_msg("SAI account policy: account changed to " .. inferred .. " from WorkDir.")
    end
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
    apply_work_dir_account(job_desc)

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
