# billing.job-charges/v1

Paired source contract: CLI PR6 and Portal PR298 are deployed in the shared
installation. A standard user's existing Identity session passed self, default
organization and another organization reads, exact-record/list agreement and
forbidden-scope rejection through the selected entrypoint. This is bounded
production evidence; it does not certify every client platform or financial scope.

An Identity resource token with `sai.billing.read` reads existing final computation
charges through `GET /v1/billing/cli/job-charges` and its exact `/{job_key}` view.
The normal user and current financial scope are resolved at Center. These reads
do not need shell access, a site-read capability or a Pilot session.

The list is bounded and ordered by recorded settlement time, with an opaque query
cursor. It discovers the existing `slurm:SITE:ACCOUNTING_INDEX` job keys. Numeric
Slurm IDs only narrow discovery: they may identify several historical executions.
An exact key never falls back to a different execution or a running estimate.

`self` is fixed to the actor's jobs within currently accessible financial wallets.
Other personal, organization and project account scopes require an exact account
or workspace selector and reuse the existing financial visibility policy. Neither
native job visibility nor a configured default account grants billing access.
An omitted selector must not expose other users' activity.

`account_id` identifies the selected account. `account` preserves an explicitly
requested canonical or legacy name; ID/workspace selection returns its canonical
name. Personal selection narrows to that account's recorded names, independently
of its payer. Organization/project scope retains the established financial
hierarchy and activity policy. Dates refer to recorded settlement in the selected
site's billing timezone; undated records appear only in unfiltered pages.
Exact keys reject all list filters, including an explicit limit.

The reader uses the existing final fact graph validator and amount presenter.
Cash/Credit/coverage/adjustment values remain hidden when that policy hides them;
gross and quantity keep their established meaning. Money remains exact decimal
text. Missing or invalid final facts never become a zero charge. Stored charges
describe computation expenses, independently of payment receipt or wallet balance.

This contract is for the batch client and Agents. It adds no terminal page,
pricing engine, financial writer, collector or duplicated ledger.
