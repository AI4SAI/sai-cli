# Product

## Register

product

## Users

SAI scientific-computing users work from terminals, the SAI console, and hosted
Agents. Researchers need to choose resources, understand running work, inspect
results and costs, and continue the same task across these entry points.
Project owners review their authorized work and budgets. Operators have a
separately authorized view of hardware, networks and failures.

## Product Purpose

The implemented product is a read-only compute CLI. Its proposed workbench
extends that client into an optional TUI sharing Portal-owned business facts
with WebUI and SAI Pilot. The product contract is described in
[the unified workbench design](docs/unified-workbench.md); the design is not an
implementation or deployment claim.

## Brand Personality

Precise, calm, capable. Follow the SAI console's product language and existing
visual system; do not define a competing WebUI theme in this repository.

## Anti-references

- A terminal job table presented as a complete workbench.
- Decorative hardware scenes with invented utilization or placement.
- Independent business rules or task histories for each client.
- A restricted chatbot replacing the full SAI Pilot Agent experience.
- Internal protocol terms, raw errors or credentials in ordinary user flows.

## Design Principles

- Keep workspace, site, billing identity and file access explicit and distinct.
- Show resource choice, execution, evidence and results as one task journey.
- Reuse authoritative services; render the same facts appropriately per client.
- Let Agents read typed data directly with the caller's actual permissions.
- Keep allocation, measured utilization, predictions and final charges distinct.
- Preserve full Agent capability inside the authorized execution boundary.

## Accessibility & Inclusion

Provide complete keyboard navigation, readable contrast, non-color status cues,
Chinese and English catalogs, terminal resize handling and reduced motion.
The Web target is WCAG 2.2 AA. Hardware information must remain usable through
semantic tables and trees without a 3D renderer.
