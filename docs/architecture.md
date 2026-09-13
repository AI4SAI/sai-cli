# sai-cli Architecture

Status: implementation baseline

## Purpose

`sai-cli` is a thin client for SAI control-plane APIs and, in a later phase,
site-local read gateways. Its job is to translate explicit user intent into a
bounded request, validate the response contract, and render JSON or a human
table. It is not an authorization engine and it is not a second scheduler.

The architecture separates three responsibilities:

| Owner | Responsibility | Explicitly does not own |
| --- | --- | --- |
| `sai-identity` | Account identity, credentials, MFA, sessions, consent, OIDC/OAuth subjects, and shared profile | Portal workspace/membership/site/billing policy or scheduler facts |
| Portal control plane | Workspace/membership, site access, compute-account ownership, policy version, authorization, and final billing facts | Identity credentials and high-frequency scheduler reads at every remote site |
| Site-local read plane | Verify a narrow capability, further restrict filters, read native site facts, cache briefly, and buffer audit records | Membership or billing policy decisions |
| `sai-cli` | Parse commands, complete a browser-approved device login when needed, renew short-lived credentials, call an authorized endpoint, validate DTOs, and render output | Raw scheduler access, broad fallback reads, or privilege expansion |

## Current and target paths

The current code release uses control-plane job visibility and
running-estimate read APIs. Its development-only non-CLI compatibility mode
still accepts a Portal credential. Managed capability/CLI routes accept only
SAI Identity-issued resource tokens:

```text
user -> sai-cli -> SAI Identity device authorization and refresh
     -> Identity access token -> Portal resource API -> authorized site reader
```

The target remote-site path separates authorization from the query hot path:

```text
                                  +---------------------------+
user -> sai-cli -- bootstrap ---> | SAI capability issuer     |
  |                               | identity + policy + scope |
  |                               +---------------------------+
  | short-lived, site-bound capability
  v
site-local read gateway -> native scheduler/storage readers
  |
  +-> bounded DTO + freshness + asynchronous audit reference
```

The transport changes, but command semantics and response DTOs stay stable.
The initial implementation must not claim that the site-local capability path
already exists.

For an interactive login-node user, the bootstrap is a one-time OAuth/OIDC
Device Authorization Grant at `sai-identity`: the browser authenticates and
approves the device, while the CLI keeps only a rotating, revocable refresh
credential. A short-lived Portal-bound access token is renewed automatically;
Portal still enforces its audience/scope and CLI read policy. SSH session
reconnects therefore do not require another login.

## Trust model

1. SAI Identity authenticates the user and issues a token for the Portal
   resource. Portal then resolves a user-facing scope into an exact scheduler
   user or account filter.
2. The CLI can only request a documented scope and can only narrow state,
   partition, object ID, and result-limit filters.
3. A site reader receives an already authorized filter or a signed capability.
4. Results are filtered again and normalized before they reach the CLI.
5. The CLI validates the normalized contract and fails closed on malformed
   payloads. It never falls back to a broad native scheduler query.

The following facts are deliberately independent:

- identity and account activation;
- command-line access;
- workspace membership and role;
- site access;
- job visibility;
- job mutation rights;
- billing visibility.

Being allowed to view a job does not imply permission to submit, cancel, hold,
requeue, change QOS, or see wallet and ledger data.

## Scope model

The first client supports these scopes:

| CLI scope | Server meaning | Selector |
| --- | --- | --- |
| `self` | Jobs owned by the current scheduler user | No account selector |
| `personal-account` | Jobs charged to the actor's personal compute account | Required account name or ID |
| `org-account` | Jobs charged to an organization account the actor may view | Required account name or ID |
| `project-account` | Jobs charged to a project account the actor may view | Required account name or ID |

There is no normal-user `all`, `ops-all`, raw `--user`, or unrestricted raw
`--account` mode. Administrative fleet views belong to a separate management
surface with separate authentication and audit policy.

### Server-bound CLI surface

The legacy Portal job endpoints use the control plane's `portal_read`
entrypoint. That entrypoint rejects disabled shell access but intentionally
allows an `agent_only` account for non-login-node read surfaces. The endpoint
is not a login-node CLI contract.

Managed capability mode uses a dedicated Portal issuer and `/cli/` routes.
Portal resolves the actor with `entrypoint=cli`, enforces shell access
`enabled`, signs a site/operation/filter-bound `sai-authz` envelope, and checks
the Bearer actor and grant again on the read route. A client header alone is
never trusted. This closes the code-level surface gap only after the matching
Portal slice, runtime dependency, signing key/epoch, and CLI package are
deployed and live-tested; local/fake tests do not close those operational
gates.

## Data and consistency

Current job state is a site-local, near-real-time fact. Authorization and
account ownership are control-plane facts. A response therefore carries both
data and freshness metadata.

The client treats these states differently:

| Condition | Client behavior |
| --- | --- |
| Valid response | Validate, then emit JSON or table output |
| Source unavailable | Return a bounded unavailable error |
| Contract invalid | Return a contract error; do not print the raw response |
| Authorization denied | Return a permission error; do not retry with a broader scope |
| Capability expired in the future local path | Stop live reads; a TUI may display clearly marked stale data |

Historical accounting and final billing are separate products. A settled
ledger is not a substitute for the live queue, and a running-cost estimate is
not a final charge. The CLI receives the estimate from Portal and never reads
pricing data or computes a price locally.

## Security invariants

- Bearer tokens and compatibility HMAC secrets never appear in command-line
  arguments, JSON output, table output, logs, or exception messages.
- OIDC refresh credentials are opaque, rotating, user-owned secrets; they are
  never sent to Portal read routes or stored in the TOML profile.
- Token caches are user-owned, use a `0700` directory and `0600` file, and are
  replaced atomically.
- Plain HTTP is rejected except for loopback development endpoints unless the
  user makes an explicit development-only override.
- HTTP error bodies are reduced to a bounded code/message pair. HTML, raw
  provider responses, native command stderr, and unknown nested fields are not
  echoed.
- Response models use an allowlist. Work directories, output paths, scripts,
  environment variables, credentials, wallet data, and raw scheduler objects
  are never forwarded by the client.
- Filters are validated locally and validated again by the server. Local
  validation is ergonomics, not an authorization boundary.

## Package boundaries

The batch CLI has no third-party runtime dependency. It uses Python 3.11+
standard-library HTTP, JSON, TOML, and filesystem primitives. A future TUI may
be shipped as an optional extra; its dependencies must not enter control-plane
or site-gateway service runtimes.

The implementation is organized around explicit boundaries:

```text
sai_cli.config       configuration and profile resolution
sai_cli.cache        protected token cache
sai_cli.auth         bearer selection and compatibility token exchange
sai_cli.transport    bounded JSON-over-HTTP transport
sai_cli.client       Portal endpoint mapping
sai_cli.contracts    stable response validation and serialization
sai_cli.render       JSON and table presentation
sai_cli.cli          command parsing and exit-code policy
```

The future site-local transport must implement the same client-facing
interface instead of adding authorization or scheduler parsing to command
handlers.

The gateway server is a separate low-privilege site-runtime role that reuses
the existing site Slurm read adapter and normalized DTO. It is not packaged in
the CLI wheel. This repository owns the client transport and shared protocol
fixtures; it must not grow a duplicate native `squeue` reader.

## Controller Submission Policy Artifact

The repository separately owns `site/slurm/job_submit.lua`. This controller
artifact validates native Slurm submissions; it is not imported by `sai-cli`,
does not enter the client wheel, and does not turn the client into a scheduler
writer.

The plugin consumes a controller-local Lua snapshot generated from a strict
control-plane projection. Portal owns account, membership, project-shape and
policy facts; the site artifact owns bounded submit-time evaluation. The
callback never calls Portal, the site-local read gateway, an authn relay, a
database, or shared storage. Full policy, snapshot and rollout semantics are in
[job-submit-policy.md](job-submit-policy.md).

## Validation boundaries

- Unit and CLI contract tests prove parsing, mapping, caching, redaction, DTO
  validation, and rendering only.
- A local fake HTTP server proves request/response integration only.
- A control-plane development-stack run proves compatibility with that stack;
  it does not prove a live scheduler or remote-site gateway.
- A live read-only canary must separately record the site, authorized scope,
  exact filters, scheduler comparison, package version, and rollback boundary.
- Production wrapper rollout is a separate deployment operation.
