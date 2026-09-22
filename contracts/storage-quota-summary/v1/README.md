# Storage quota summary v1

Portal owns the schema and sample at `contracts/storage-quota-summary/v1`.
These are byte-identical compatibility artifacts, not runtime dependencies.
The CLI uses an explicit standard-library allowlist and never imports Portal.

The read is an existing Portal quota observation: `state` describes delivery,
`observed_at` describes the usage sample, and `quota_updated_at` describes the
effective quota. No field promises that the sample is live. All nullable fields
are present; unknown is distinct from zero. Remaining capacity may be negative
when usage exceeds effective quota. Targets do not replace effective quota.

Paths, directory management/actions, entitlement details, native quota subjects,
wallet and ledger fields are excluded. Clients ignore unknown additive fields
after validating the allowlist. Independent `sai.storage.read` consent and
server-side membership/site policy are required.

SHA-256 schema: `fe9220ff3cdc671dbc44bf96c8c30001956c966abe727557b7cebf011d3b7c9e`.
SHA-256 sample: `c02dcdc5323c58772fb01a1cb27084b8a46ae5dc7c2188b37056dab4ec39ee6f`.
The sample is synthetic. Producer: `AI4SAI/sai-portal` commit
`72360c70849d704c7d585536bde067a425d20201`; Identity optional scope registration:
`AI4SAI/sai-identity` commit `cb1bc674ddaf4d53ef2c02add2cc70671f4eff21`.
