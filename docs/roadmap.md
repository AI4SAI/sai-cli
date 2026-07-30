# Roadmap

This roadmap replaces the CLI implementation portion of the former Portal
design taskboard. Portal-specific authorization service work remains in the
Portal repository.

## Milestone 0.1: read-only jobs CLI

- [x] Installable Python package and `sai` console entry point
- [x] Profile, environment, and command-line configuration precedence
- [x] Protected short-lived token cache
- [x] Existing Bearer token and managed-node HMAC compatibility bootstrap
- [x] `sai jobs list` and `sai jobs show`
- [x] Stable JSON and deterministic table rendering
- [x] Scope/filter validation and no normal-user all scope
- [x] Bounded error mapping and response redaction
- [x] Unit, CLI contract, fake HTTP integration, package, and disclosure tests

Acceptance boundary: local tests and fake HTTP only. This milestone does not
prove a development stack, live scheduler, remote site, package deployment, or
production wrapper.

## Milestone 0.2: control-plane compatibility

- [ ] Cross-repository contract fixture shared with the Portal API
- [ ] Development-stack read-only smoke for self and one account scope
- [ ] Browser/device login design for unmanaged clients
- [ ] Shell completion and package metadata

Acceptance boundary: development control plane. It does not prove live site
facts or production deployment.

## Milestone 0.3: optional TUI

- [ ] Optional TUI dependency group
- [ ] Jobs, resources, partitions, QOS, and usage navigation model
- [ ] Local-state keyboard interactions and asynchronous refresh
- [ ] Stale-while-revalidate, cancellation, pagination, and bounded empty/error
  states
- [ ] Headless interaction and fake-delay latency tests

Acceptance boundary: TUI contract against fake or development endpoints. It
does not prove real placement, topology, rate data, or production latency.

## Milestone 0.4: site-local capability transport

- [ ] Versioned capability/query/response schemas
- [ ] Control-plane issuer compatibility vectors
- [ ] Local verifier, filter narrowing, cache isolation, and audit reference
- [ ] Client capability cache and renewal single-flight
- [ ] Local-gateway transport behind existing commands
- [ ] Development-stack protocol smoke

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
