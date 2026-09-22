# Native quota observation contract

Status: merged implementation; deployment and live acceptance are separate.

Producer: Portal `1dc290cffba86d587f68ab0921071f22aa3a486e`. Deploy the matching
issuer and native gateway before enabling this consumer's native source.

`storage.native-quota/v1` contains only authorized physical quota subjects read
on demand. It is independent of `storage.quota-summary/v1`, which describes
stored business observations and desired/effective quota delivery.

- `coverage=authorized_quota_subjects` does not mean a complete organization pool.
  Shared root and visible independent directory subjects remain separate rows;
  sponsored homes and funding baselines are not silently added or subtracted.
- Counters are exact unsigned decimal strings, with byte/inode units. Native
  limit zero means unlimited. Missing or inaccurate native counters fail the read;
  they are never replaced by zero or a stored sample.
- `observed_at` is each native query's completion time; `as_of` is the response
  completion time. These are UTC, not a claim of an atomic cross-subject snapshot
  or instantaneous filesystem counters. This path stores no observation history.
- Public references identify quota/allocation incarnations and mounts. Native
  project IDs, filesystem source paths, commands and raw output are excluded.
- All modeled fields are required. Consumers discard additive unknown fields,
  validate exact requested site/workspace, distinct quota refs, safe text and
  integer bounds (uint64 counters; KiB-to-byte values up to uint64 times 1024).
- A failure returns a bounded error, with no partial successful response and no
  fallback to the central observation. Capability renewal does not cache data.

`schema.json` and `sample.json` are shared compatibility artifacts. Synthetic
vectors and local subprocess/HTTP tests do not prove a deployed Lustre client.
