# Portal Job Visibility API Contract

Status: consumed by the phase-one client

This document records the control-plane contract that `sai-cli` currently
consumes. The control plane remains the source of truth for authorization and
may evolve independently, so contract changes require compatibility tests in
both repositories.

## Authentication

User endpoints require:

```http
Authorization: Bearer <short-lived-token>
```

Managed-node compatibility bootstrap uses:

```text
POST /v1/token?username=...&ts=...&nonce=...&key_id=...&sig=...
```

Successful bootstrap response:

```json
{
  "token": "redacted",
  "expires_at": 1785427200,
  "can_access_portal": true,
  "can_access_mis": false
}
```

The CLI never prints or logs `token` or `sig`.

## List jobs

```text
GET /v1/slurm/jobs
```

Supported query parameters:

| Parameter | Required | Contract |
| --- | --- | --- |
| `site_id` | yes | Site token |
| `cluster_id` | no | Optional cluster token |
| `scope_type` | yes | `self`, `personal_account`, `org_account`, or `project_account` |
| `slurm_account_id` | account scopes | Exactly one account ID or name is required for every account scope |
| `slurm_account_name` | account scopes | Exactly one account name or ID is required; server authorizes it |
| `partition` | no | Narrowing filter |
| `states` | no | Comma-separated narrowing filter |
| `limit` | no | Integer from 1 through 500, default 100 |
| `source_preference` | no | Currently fixed to `live` |

The client does not send raw `user`, arbitrary query parameters, or a
non-live source preference.

The current route calls Portal's `portal_read` policy entrypoint. It rejects
`LinuxShellAccess.DISABLED` but permits `AGENT_ONLY`. This is valid for Portal
or Agent read-only surfaces, but it is not the final login-node CLI contract.
A dedicated endpoint or surface-bound capability/token must enforce
`LinuxShellAccess.ENABLED` before production CLI wrappers are enabled.

## Show one job

```text
GET /v1/slurm/jobs/{job_id}
```

It accepts the same site, cluster, scope, account, states, and source fields as
the list endpoint. It does not accept partition or limit. A `404` means the job
does not exist or is not visible; the client must not distinguish those cases.

## Response

Both endpoints return the same envelope. The detail endpoint returns one item.

```json
{
  "site_id": "site-a",
  "cluster_id": "cluster-a",
  "scope": "project_account",
  "visibility_role": "read",
  "slurm_user": null,
  "slurm_account": "project-example",
  "items": [
    {
      "job_id": "12345",
      "array_task_id": null,
      "name": "simulation",
      "slurm_user": "alice",
      "slurm_account": "project-example",
      "state": "R",
      "state_label": "running",
      "priority": 1000,
      "submit_time": "2026-07-31T00:00:00Z",
      "start_time": "2026-07-31T00:01:00Z",
      "elapsed_seconds": 3600,
      "run_wait_seconds": 3600,
      "partition": "gpu-standard",
      "qos": "normal",
      "nodes": 1,
      "slots": 8,
      "gpus_per_node": 1,
      "mem_per_unit": "16G",
      "reason_or_nodelist": "compute-node"
    }
  ],
  "count": 1,
  "freshness": {
    "source": "squeue",
    "queried_at": "2026-07-31T01:01:00Z"
  }
}
```

Every item must contain exactly the documented semantic field set after client
normalization. Values may be null where the scheduler has no fact. Unknown
server fields are not forwarded by the CLI.

The response must not expose:

- work directories, stdout/stderr paths, submit scripts, commands, or
  environment variables;
- raw scheduler or site-agent payloads;
- wallet, balance, pricing, ledger, payment, or refund fields;
- credentials, internal secrets, or raw provider errors.

## Bounded errors

The control plane may return a string `detail` or an object containing a short
`code` and user-safe `message`. The CLI maps HTTP status and bounded error code
to its stable exit categories. It does not echo arbitrary nested bodies.

Expected examples include source unavailable, source contract invalid,
authentication failure, authorization denial, unsupported query, and job not
found or not visible.

## Change discipline

- Additive response fields are allowed; older clients ignore them.
- Removing or changing a documented field requires a versioned migration.
- Adding a query parameter does not permit the CLI to send it until the client
  contract is reviewed.
- A local fake server test does not establish live scheduler compatibility.
