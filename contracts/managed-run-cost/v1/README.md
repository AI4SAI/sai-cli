# Managed Run final cost, v1

Implemented paired read contract. Portal owns production and authorization.
CLI/TUI, the console and SAI Pilot consume the same explicit per-Run read.
It does not change the compute-only `compute.run/v1` metadata contract.

The response binds the actor-owned Run, explicit project workspace and site.
`source=portal_final_billing` describes persisted billing facts; `queried_at`
is the query time, not a new scheduler observation. No caller-selected payer,
wallet, accounting index or another actor is accepted. Internal financial
record IDs, paths and provider errors are not returned.

`settled` requires the exact Run/accounting incarnation and the canonical final
JobFact/Ledger/LineItem/Usage/Allowance graph. It does not require a settlement
queue row. `settled_at` is the actual billing fact timestamp when known, not the
usage end time. `pending` means final facts are not yet available; `unavailable`
means their binding or completeness cannot be established. `not_chargeable`
requires the existing exact zero-usage decision, current matching accounting
evidence and the complete shared absence-of-economic-writes check. Cancellation,
missing facts and zero cash alone never imply that status. Non-settled amounts,
unit and settlement time are null, including `not_chargeable`.

Amounts are nonnegative decimal strings with eight fractional digits. Gross
is the standard usage amount. Cash, SAI Credit equivalent, reserved coverage
and price adjustment retain the existing billing semantics; SAI Credit points
are independently supplied by the producer. Clients never calculate prices,
convert Credit or infer missing values. Quantity uses the returned unit.

Current project financial visibility is independent of Run READ and file READ.
When `cash_visible=false`, settled gross and quantity remain visible; cash,
Credit and funding components are null. No client may switch to organization
scope to obtain those hidden fields. CLI cost reads require `sai.billing.read`
as well as existing current Run/CLI read admission. Missing billing permission
does not invalidate independently readable task metadata. Revoked Run/project
access still clears protected task observations.

The explicit routes are `/v1/compute/cli/runs/{run_ref}/billing` and
`/v1/account/compute/runs/{run_ref}/billing`, with only workspace_key/site_id.
The console Run link accepts an explicit `view=cost`, mutually exclusive with
file-selection parameters. The link carries no amounts or financial record IDs.
Pilot uses `run_cost` via its existing `run.cost` read transport and browser
`run.billing` action. Existing Session identity/current project READ is checked
again; model activation remains required for MCP, while the authorized browser
history path retains its existing independent activation policy. No request
starts/renews a runtime, submits/cancels a job, or writes financial facts.

Unknown additive response fields are ignored until allowlisted by consumers.
Invalid types, money, state combinations and bindings fail closed. Refresh
replaces a bounded observation; stale replies after context changes cannot
restore previously cleared amounts. Sample data is synthetic. Local validation
and paired source merge do not establish production deployment or live billing.
