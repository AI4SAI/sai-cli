# Roadmap

This roadmap replaces the CLI implementation portion of the former Portal
design taskboard. Portal-specific authorization service work remains in the
Portal repository.

## Site Artifact: controller submission policy

- [x] Minimal `job_submit.lua` submission and modification policy
- [x] Strict account/GPU policy projection renderer
- [x] Actual-Lua behavior tests without a Python policy reimplementation
- [x] Snapshot, hot-reload, rollback, failure and performance contracts
- [ ] Portal authoritative projection producer
- [ ] Matching-version disposable-controller compatibility test
- [ ] Live controller canary, peak-rate benchmark and TaskProlog cutover

Acceptance boundary: repository Lua/runtime tests only. The unchecked gates are
required before enabling `JobSubmitPlugins=lua` or removing TaskProlog policy.

## Milestone 0.1: read-only jobs CLI

- [x] Installable Python package and `sai` console entry point
- [x] Profile, environment, and command-line configuration precedence
- [x] Protected short-lived token cache
- [x] Existing Bearer token and unmanaged compatibility HMAC bootstrap
- [x] `sai jobs list` and `sai jobs show`
- [x] `sai jobs cost` against the independent Portal running-estimate DTO
- [x] Stable JSON and deterministic table rendering
- [x] Scope/filter validation and no normal-user all scope
- [x] Bounded error mapping and response redaction
- [x] Unit, CLI contract, fake HTTP integration, package, and disclosure tests

Acceptance boundary: local tests and fake HTTP only. This milestone does not
prove a development stack, live scheduler, remote site, package deployment, or
production wrapper.

## Milestone 0.2: control-plane compatibility

- [x] Server-bound `/v1/slurm/cli/*` and `/v1/billing/cli/*` routes with an
  exact `sai-authz` capability and `entrypoint=cli` shell-access check
- [ ] Shared cross-repository request/response fixture (the two repositories'
  focused vectors are aligned, but no single shared artifact is published yet)
- [ ] Production issuer key/epoch deployment and authenticated devstack smoke
- [ ] Development-stack read-only smoke for self and one account scope
- [ ] Independent Portal settled-billing read contract (`billing.settled.read`)
  and a separately reviewed CLI command
- [ ] Browser/device login via the SAI Identity OIDC Device Authorization Grant
  (the client-side protocol candidate is local; Identity provider/client
  registration, Portal resource-token consumption, and live authentication
  remain gates)
- [ ] Shell completion and package metadata

Acceptance boundary: development control plane. It does not prove live site
facts or production deployment.

## Milestone 0.3: optional TUI

- [ ] Optional TUI dependency group
- [ ] Jobs, resources, partitions, QOS, and usage navigation model
- [ ] TUI running-usage estimate view; the batch `jobs cost` view already
  exposes `final=false`, `as_of`, freshness, price revision, and uncertainty
- [ ] Estimate-to-final replacement without duplicate display or aggregation
- [ ] Local-state keyboard interactions and asynchronous refresh
- [ ] Stale-while-revalidate, cancellation, pagination, and bounded empty/error
  states
- [ ] Headless interaction and fake-delay latency tests

Acceptance boundary: TUI contract against fake or development endpoints. It
does not prove real placement, topology, rate data, or production latency.

## Milestone 0.4: site-local capability transport

- [ ] Versioned capability/query/response schemas
- [ ] Control-plane issuer compatibility vectors
- [ ] Site-local billing-visibility capability; the Portal running-estimate
  HTTP contract is implemented, but job visibility alone must not grant it
- [ ] Shared scheduler collector snapshot for jobs and usage estimates, with
  2-15 second TTL, request coalescing, ETag, and freshness
- [ ] Cross-repository site-runtime gateway fixture for verifier, filter
  narrowing, cache isolation, and audit reference; the gateway server is not a
  CLI-wheel module
- [ ] Client capability cache and renewal single-flight
- [ ] Local-gateway transport behind existing commands
- [ ] Development-stack protocol smoke
- [ ] Contract fixture usable by CLI/TUI, Portal relay, and a separately owned
  site-local read-only Web client
- [ ] Separate site-telemetry batch fixture proving interactive reads cause no
  exposure writes and persistence does not follow the 2-15 second UI cadence

Acceptance boundary: protocol implementation. It does not prove a live remote
site or production package.

## Milestone 0.5: packaging and canary

- [ ] Login-node package and optional TUI extra
- [ ] Package-managed legacy wrapper templates
- [ ] Install manifest, forbidden-content guard, and rollback artifact
- [ ] Read-only live scheduler comparison with an authorized sample scope
- [ ] Canary latency, freshness, audit-backlog, and rollback evidence

Production rollout and fleet-wide replacement require a separate operations
plan and approval.

The batch-only login-node Debian package, full-SHA manifest, and canary run card
are implemented as local candidates. These checkboxes remain open until a
clean pushed commit is built and target install/readback/rollback evidence is
captured; local packaging tests do not mark production complete.
