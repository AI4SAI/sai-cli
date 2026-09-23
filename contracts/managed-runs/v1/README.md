# Managed Run reads, v1

Status: implemented read contract. Source and local validation cover authorized
Portal Run receipts and bounded file reads, not deployment or live-site proof.
Portal owns the producer; the schema, samples and this document are identical in
the Portal and CLI repositories.

| Schema file | Response version | Meaning |
| --- | --- | --- |
| `list.schema.json` | `compute.runs/v1` | A bounded page of the actor's managed Run receipts |
| `detail.schema.json` | `compute.run/v1` | One authorized managed Run receipt |
| `log.schema.json` | `compute-run-log.v1` | One bounded read from the Run's declared stdout or stderr |
| `artifacts.schema.json` | `compute-run-artifacts.v1` | One page of current files under the Run's declared outputs |

Each schema has a corresponding `*.sample.json` with synthetic identifiers.
Unknown additive response fields are permitted by the schemas. Consumers
recursively allowlist modeled fields before rendering or returning data; an
additive field never becomes a credential, path, command or new permission.

## Run receipts and authority

Every response binds an explicit `project:<id>` workspace and site. List and
detail use `source=portal_run_receipts` and UTC `queried_at`. They read the
existing durable ComputeRun records; they do not query `squeue`, infer current
allocation or price a job. A recent query time is not a fresh scheduler
observation: `last_observed_at` can be null or older.

The actor may read only their own Runs within a currently readable project and
site. Portal resolves active/effective membership and current workspace access
on every request, including detail and continuation pages. Another member's
Run, a different workspace/site or a removed membership does not inherit access.
READ membership can read these records without compute-submit authority.
A stopped or replaced scheduler account does not erase an otherwise authorized
historical receipt. Submission permission, payer activity, a Pilot Session,
model budget and ExecutionGrant are not prerequisites for this read surface.
The CLI's identity/resource-token and shell admission remain separate checks.

List pages contain at most 100 items. `next_cursor` is an existing `run_ref`
or null; `has_more=false` requires null. A continuation is still scoped to the
current actor, workspace and site. No all-user, arbitrary actor or payer
selector is exposed.

A Run item contains only the fields in the schema. `title` is a nullable
entrypoint basename, not a workspace path. Embedded C1 characters remain valid
filename data in `title`; terminal output must escape them without changing the
JSON value. C0, DEL and slash remain invalid in a title. State, revision and
timestamps are
stored receipt facts; `canceling` and `needs_attention` retain their existing
read-model meaning. `scheduler_ref` is an opaque nullable reference, not a
client-created job/attempt identity. No grant, Pool/Session credential, wallet,
ledger, frozen script or raw error message is returned. `error_code` is a
bounded code, not provider text.

## Logs and current output files

Log and artifact responses reuse the existing ComputeRun readback DTOs and add
`workspace_key` and `site_id`; their schema versions are unchanged. Metadata
visibility does not grant file access. Every log/artifact request independently
resolves current applied file READ access to the Run's frozen workspace mount.
The currently authorized root must equal the frozen root. A pending/revoked
ACL, changed mount or inaccessible file root fails closed before a site read.
The actor, Run and workspace/site binding are checked again for each request.

Reads use the existing dedicated interactive-read site adapter. This is not the
capability-only job gateway. The center retains its protected read credential;
the CLI receives no site secret and never calls the site agent or filesystem
directly. Missing configuration or failed reads do not fall back to SSH,
another source, a copied file or an empty successful response. Reading does not
create, renew, submit or cancel a Run, Session or model activation, and the
managed read path must not perform database DML.

Log `content` is valid UTF-8 text bounded to 65,536 encoded bytes, also bounded
by the requested `max_bytes`. Newlines and other log characters remain data.
JSON Schema's `maxLength` counts code points; clients must additionally check
the UTF-8 byte count. Successful JSON preserves the content. Terminal rendering
must neutralize unsafe controls without executing terminal sequences; it must
not silently delete legitimate multiline log content during DTO validation.
`cursor` and `next_cursor` both remain `log-<stream>-<offset>` strings,
including the final page. Offsets bind the requested stdout/stderr stream and
range from zero to the existing signed 64-bit maximum. An unavailable log has
empty content and remains incomplete; absence is not a successful empty file.

Artifact pages contain at most 100 files. Cursors retain the existing decimal
`0` or 1–9 digit nonzero-leading form; a complete page has null
`next_cursor`. Each item carries `artifact_ref`, `display_name`,
`relative_path`, `kind=file`, `size_bytes` and `modified_at_ns`. Sizes
and nanosecond times are exact integers, not floating-point approximations or
booleans. Unicode and spaces in filenames are valid; identifier-token rules
must not be imposed on paths. Paths are normalized workspace-relative POSIX
paths within declared output roots. The existing producer rejects C0/DEL,
traversal, backslashes and sensitive path components; terminal consumers also
render C1 characters safely while preserving the actual locator.

Both file DTOs preserve `freshness.source=site-agent` and UTC
`freshness.queried_at`, equal to `observed_at`. These timestamps describe
the read, not immutable content creation. Artifact references identify a Run
and relative path; they are not content digests. Files can change or disappear
between listing and opening. Reused output directories are not sealed
execution-attempt archives.

The existing Pilot client already opens an authorized result with its bound
root Session and the producer's explicit relative path through the upstream
native document preview. Display labels are not locators. This contract adds
no preview service, file browser, large-file copy, arbitrary download URL or
automatic Pilot activation.

## Validation beyond JSON Schema

Consumers also enforce exact request workspace/site/Run/stream binding, list
limits and cursor continuity, actual UTC calendar dates, native integer types,
UTF-8 byte limits, declared-root/file authority and the existing cursor/page
semantics. JSON Schema alone does not express all these checks. File names and
log text are untrusted display data, while the server remains the authorization
owner.

Local schema, negative-case and HTTP checks do not establish real MariaDB,
Slurm, site-agent UID/ACL, shared storage, Identity-provider or production
acceptance. Those gates must be reported separately.
