# Runtime Design

Status: phase-one commands frozen

## Command surface

The first release is read-only and exposes two commands:

```bash
sai jobs list --site site-a
sai jobs list --site site-a --scope org-account --account org-example
sai jobs list --site site-a --scope project-account --account project-example \
  --states R,PD --partition gpu-standard --limit 100
sai jobs show 12345 --site site-a
sai jobs show 12345 --site site-a --scope project-account \
  --account project-example
```

`--format json` is the default. `--format table` is intended for a person at a
terminal. JSON is always written to stdout; diagnostics are written to stderr.

The first release does not implement:

- job submission, cancellation, hold, requeue, suspend, or QOS changes;
- normal-user all-site or all-account queries;
- raw scheduler user filters;
- automatic fallback from live state to broad accounting queries;
- node topology, placement, storage, usage estimate, or TUI commands.

Unimplemented command families remain in the roadmap rather than appearing as
placeholders that return fake data.

The current Portal endpoint uses `portal_read` authorization and can accept an
`agent_only` account. Production login-node rollout remains blocked until a
server-verifiable CLI surface enforces shell access `enabled`; client headers or
local checks cannot establish that authorization boundary.

## Scope selection

`--scope` accepts `self`, `personal-account`, `org-account`, or
`project-account`.

- `self` rejects account selectors.
- `personal-account`, `org-account`, and `project-account` require exactly one
  of `--account` or `--account-id` under the current Portal contract.
- The CLI maps hyphenated user-facing values to the control-plane underscore
  values. The server remains authoritative.

`--states` is a comma-separated allowlisted token list. `--partition` only
narrows the result. `--limit` is constrained to the API range of 1 through 500.

## Configuration

Configuration precedence is:

1. command-line non-secret options;
2. environment variables;
3. the selected TOML profile;
4. built-in non-secret defaults.

Default config path:

```text
${XDG_CONFIG_HOME}/sai/config.toml
~/.config/sai/config.toml
```

Example:

```toml
default_profile = "default"

[profiles.default]
base_url = "https://portal.example.org"
site_id = "site-a"
username = "alice"
key_id = "managed-login"
timeout_seconds = 10
```

Tokens and shared secrets are rejected in the TOML file. They must be supplied
through a short-lived environment or a managed node credential mechanism.

Relevant environment variables:

| Variable | Purpose |
| --- | --- |
| `SAI_API_BASE_URL` | Control-plane base URL |
| `SAI_SITE_ID` | Default site |
| `SAI_PROFILE` | Profile name |
| `SAI_API_USERNAME` | Actor username for compatibility token exchange |
| `SAI_API_KEY_ID` | Managed client key identifier |
| `SAI_TOKEN` | Already-issued short-lived Bearer token |
| `SAI_API_SHARED_SECRET` | Managed-node compatibility HMAC secret |
| `SAI_API_TIMEOUT` | HTTP timeout in seconds |
| `SAI_ALLOW_INSECURE_HTTP` | Development-only explicit HTTP override |

## Authentication

Token selection order is:

1. use `SAI_TOKEN` for the current process without writing it to disk;
2. reuse a valid protected cache entry;
3. on a managed login node, exchange a compatibility HMAC request at
   `POST /v1/token` and cache only the returned short-lived Bearer token.

The HMAC canonical string is part of the existing Portal compatibility
contract:

```text
username + "\n" + unix_timestamp + "\n" + nonce + "\n" + key_id
```

The compatibility secret is not a general desktop login mechanism. A future
interactive browser/device authorization flow should replace it for unmanaged
clients. The CLI must not accept a secret or Bearer token as a command-line
argument because process listings and shell history are not secret stores.

## Token cache

Cache path precedence is:

```text
${XDG_RUNTIME_DIR}/sai/token-cache.json
${XDG_CACHE_HOME}/sai/token-cache.json
~/.cache/sai/token-cache.json
```

Requirements:

- directory mode `0700`, file mode `0600`;
- no symbolic-link cache files;
- atomic same-directory replacement;
- entries keyed by normalized base URL, username, and key ID;
- a token is considered expired before its actual expiry to leave request
  margin;
- malformed or weak-permission caches fail closed with a bounded diagnostic.

## HTTP behavior

- The base URL must be HTTPS unless it resolves syntactically to a loopback
  host or the development override is explicit.
- Requests have a bounded timeout and response-size limit.
- Each request carries a client-generated request ID.
- Redirects are not used to broaden trust to another host.
- Non-2xx responses are mapped to stable CLI error categories.
- Only a bounded server `detail.code`, `detail.message`, or string detail is
  eligible for display, after secret-pattern redaction.
- A non-object JSON payload is a contract failure.

## Output contract

JSON output contains only the stable job visibility fields documented in
[portal-api-contract.md](portal-api-contract.md). Unknown response fields are
ignored after validation instead of being copied to stdout.

Table mode keeps the established SAI meanings:

- `GPU` is GPU count per node, not total GPU count.
- `MemPerU` is host memory per GPU or CPU logical unit.
- `Slots` can describe requested tasks while pending and allocated CPU slots
  while running.
- `Reason/Nodelist` is a pending reason or the allocated node expression,
  depending on state.

Table rendering uses no ANSI color by default so redirects and wrapper output
remain deterministic.

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Success |
| `2` | Command or configuration error |
| `3` | Authentication failed or credentials unavailable |
| `4` | Authorized identity lacks the requested permission |
| `5` | Object not found or not visible |
| `6` | Authorized source temporarily unavailable |
| `7` | Server/client contract invalid |
| `8` | Network or timeout failure |

In JSON mode, errors are emitted as a small JSON object on stderr. In table
mode they are emitted as one plain diagnostic line.

## Legacy wrapper migration

Site-specific legacy commands may later become package-managed wrappers around
the canonical CLI. A wrapper may translate an old command name and select table
format, but it must not query the scheduler directly or implement authorization.

The rollout sequence is: inventory and checksum, stage the new package, canary
through an explicit path, atomically switch package-managed wrappers, validate,
and retain a package-level rollback. This repository does not authorize manual
editing of production command directories.
