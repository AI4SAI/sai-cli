# Authorized directory discovery v1

The response is generated from `FileWorkspaceDiscoveryOut` in
`sai_core/api/schemas/file_workspace_discovery.py`.

Each page contains the current actor's readable whole directory roots at one
site. Discovery reuses `file_workspace_roots(requested_role="read",
whole_roots=True)`. It reads existing authorization and directory facts without
walking the filesystem, requesting credentials, or reading wallets. Legacy
subdirectory grants do not become whole-root entries. Revocation is checked
again on each page and on every later operation.

The default page size is 50, with a maximum of 100. `next_cursor` is the existing
opaque keyset cursor. A page may contain no items and still have a cursor because
unauthorized candidates are filtered after the bounded candidate query. Continue
only when needed, retaining the actor and site. An invalid or revoked cursor
requires restarting from the first page. Database and inconsistent-fact errors
remain errors.

`workspace_ref` selects the directory. `workspace_mount_ref` binds its existing
mount lineage. `scope_ref` and `scope_label` identify its personal, organization,
or project scope. `label` uses the existing authorized directory presenter.
`path_label` is the registered relative path, while `path` is its canonical
absolute path. `account_workspace_key` identifies the account that owns the
directory. Its presence grants no account use.

`actions` are permission gates for using this directory. Browse and reference
require current read authority. Working directory, editing, terminal and BYOK
require write authority. SAI model and compute also require current permission
to use the owning account. An explicitly inactive workspace site denies those
account actions. These gates contain no balance, subscription, model allowance,
Slurm association, queue or native execution readiness promise. The existing
execution entrypoints recheck the current identity, account, site provisioning,
resources and funding before issuing grants or starting work.

An allowed action has `reason=null`. Denials use `read_only`,
`account_permission_required`, `needs_project_compute_permission`, or
`workspace_site_unavailable`. Only a current project member lacking project
compute permission receives `needs_project_compute_permission`.

The authenticated CLI route uses the existing `sai.ssh.mounts.read` metadata
consent. This directory listing does not perform SSH eligibility checks or issue
SSH credentials. `storage.read` remains quota consent and does not grant this
directory metadata. Portal and Pilot use their existing authenticated actor and
site context. The Agent request `PilotDirectoryAgentCallIn` reuses
`PilotAccountAgentCaller` and the original Session transport proof, with
`schema_version="sai-pilot-directory-read.v1"`.

Generate `schema.json` from `FileWorkspaceDiscoveryOut.model_json_schema()` with
the JSON Schema 2020-12 `$schema` declaration, and validate `example.json` with
that same model. `agent.schema.json` is generated
from `PilotDirectoryAgentCallIn.model_json_schema()` with the JSON Schema
2020-12 declaration. Response labels and paths are data, never shell fragments
or authorization selectors.

Browser callers use the existing `POST /v1/internal/pilot/browser/read` envelope
with `body={"action":"directory.list","limit":50,"cursor":null}`. Native Agent
callers use `POST /v1/internal/pilot/directories/read` and `agent.schema.json`.
The service must match the caller cell/site and validate the current native
generation and original Session transport. This read needs no default-account
management delegation and issues no execution grant. CLI callers use
`GET /v1/account/cli/file-workspaces?site_id=<site>&limit=50`, adding the returned
`cursor` when continuing. All three return the same page and private/no-store.

Paired consumers must also understand `model_payment.state=permission_required`
and reason `needs_project_compute_permission`. Actual project SAI model and
managed-compute requests reject with 403 and this reason. No missing compute
permission is converted into a server outage or a different payer.
