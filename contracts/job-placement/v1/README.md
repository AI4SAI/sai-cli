# Registered job-node placement, v1

`jobs.placement/v1` requires its own exact-job `jobs.placement` capability.
The ordinary allocation/list capabilities do not grant placement. Portal only
issues it when the site explicitly opts in to publishing approved registration
information to currently authorized job readers. It reuses current membership,
site and SELF_ONLY filters; no file, submit, money or administrator right follows.

The response embeds the complete `jobs.allocation/v2` snapshot used to resolve
its nodes. Consumers validate that existing contract and exact request binding,
then require `nodes` to have the same names and order. If allocation is unknown
or absent, `inventory` is null and `nodes` is empty. If allocated, `inventory`
is required, even when all returned nodes are unmapped.

Each node has `recorded`, `unmapped` or `expired` status. Only `recorded` carries
a registration. This is an operator-recorded association, not live proof that
the same physical incarnation still runs under that node name. Missing or
expired registrations do not become zero U or fabricated assets.

A registration contains owner-provided asset/incarnation references, safe label,
verified_at and valid_until. A known rack has a safe ref/label and positive
u_start/u_height, using U numbers increasing from the bottom. U fields are each
1–100 and their end is at most 100; the producer also checks the actual recorded
rack height and overlap. Without rack, placement_ref is null. The public result
does not expose full cabinet height, empty bays, neighbours or total occupancy.

Time comparisons use real UTC instants, including up to six fractional digits:
verified_at <= published_at <= allocation.freshness.observed_at < valid_until
<= inventory.expires_at. The producer also checks current time. Republishing
does not refresh verified_at. A renderer clears registration highlights on
expiry; it does not automatically send more reads or modify allocation facts.

Inventory revision is the exact published bundle digest and generation is a
positive JSON-safe integer <= 9007199254740991. A protected current publication
head pins that bundle. Each request checks the head before/after association,
signature, site/cluster, time and capability. Invalid, revoked, expired or changed
publication returns a bounded error with no old-cache fallback. Original
allocation reads remain independent.

Consumers recursively drop unknown fields and check ref/label types, native
integers, status/null consistency and times. Repeated rack refs have consistent
labels, non-overlapping returned U ranges; repeated asset/incarnation bindings
are invalid. This response contains only allocated nodes, not a whole-site
asset export. Normal rendering uses schematic cabinet fragments without
showing undisclosed gaps as free space. It does not infer room coordinates,
GPU slots, CUDA/NVML identifiers, utilisation or a permanent job attempt.

Schema and sample are paired across Portal, CLI and Pilot. The sample is
synthetic and fixed in time; tests of live display should set their clock or
refresh fixture timestamps. Local tests do not establish asset verification,
publication at a site, gateway deployment or production acceptance.
