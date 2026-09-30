# Managed Run registered placement, v1

Implemented read contract. This explicit read binds the current native
allocation and operator registrations to an actor-owned managed Run. It reuses
jobs.placement/v1 and jobs.allocation/v2 without turning scheduler indices into
physical GPU identities or registration into measured machine truth.

Clients select only Run/project/site. Portal checks current Run READ and the
site placement flag, derives native user/account/job/correlation/accepted time,
and signs the independent interactive-run-read-grant.v1. The outer sai-authz
envelope and exact jobs.placement operation are unchanged. Ordinary job reads
retain their own v1 grant. Unknown/old consumers reject the stronger grant;
no retry may strip Run constraints or accept ordinary placement as Run proof.

Gateway reuses the existing unprivileged exact native allocation reader and
signed inventory. Before output it verifies owner/account/cluster/job/marker,
submission bound and before/after runtime SLUID, restart, resize and allocation.
The initial native binding targets Slurm 26.05.1 / data_parser v0.0.45.
The wrapper always contains the original complete placement DTO. Execution is
null only for not_allocated; otherwise it carries runtime SLUID and native
submit/start/restart/resize evidence. These fields must agree with the nested
allocation. Runtime SLUID is not a physical machine or accounting identity.

An absent scheduler reference, a missing/reused job, changed binding or source
failure is a bounded error, not historical placement or a successful empty
list. Pending/terminal native not_allocated stays a real native observation.
HTTP consumers check inventory/recorded-location deadlines again after parsing;
an observation that expires in transit is rejected without a weak retry.
Current READ does not imply file, payer, submit, model renewal or asset write
permissions. Run revocation clears protected facts; independently disabled
placement clears only this view. Inventory expiry clears location details
without changing the recorded allocation. No cached or broad source fallback.

Routes: GET /v1/compute/cli/runs/{run_ref}/placement and the browser counterpart
/v1/account/compute/runs/{run_ref}/placement, with workspace_key/site_id only.
Agent run_placement uses run.placement through the existing Session-bound read
transport. Pilot browser action is run.placement.read. TUI/Web/Pilot reads are
manual snapshots. W continuation may add view=placement to the same Run URL;
file selection, cost and stats modes remain mutually exclusive. No device IDs,
metrics or capabilities are carried in the URL.

The samples are synthetic. The schema embeds the unchanged existing placement
definitions for standalone consumption. Consumers reuse their current nested
placement parser and renderer, then check wrapper scope/execution agreement.
The source slice adds no GPU telemetry, geometry, new native helper, collector,
state database or scheduler/asset mutation. Local proof is separate from a
paired production installation and real asset verification.
