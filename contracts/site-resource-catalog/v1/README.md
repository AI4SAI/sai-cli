# Published site catalog v1

Portal owns the schema and example under `contracts/site-resource-catalog/v1`.
These files are byte-identical snapshots used by CLI compatibility tests. The
runtime validates its explicit allowlist using the standard library; it does
not download schemas or import Portal code. Pilot and WebUI consume the same
published catalog, while Pilot retains its separate scheduler preparation data.

Producer commit: `0351f46ab3f755a815cee68b9bf489f22f48174c` in `AI4SAI/sai-portal`.
SHA-256: schema `4a67c368f73efb67d9aabc2614f6a6231f68ce482867b112374c27f64660884a`;
sample `013c23892f8ec4c31a97ae45f3e56aabffdd0003a4535ba437b691e92468cdcc`.

Schema: `site.resource-catalog/v1`. `catalog.json` contains synthetic data only.
Unknown additive fields are ignored by clients; schema changes and updated
snapshots require coordinated producer/consumer review. Nullable fields are
required in responses and retain null, never a guessed zero.

The catalog describes published products. It does not report current free
capacity, file access, job submission eligibility, expected deductions or
settled charges. Each price retains its own server-provided unit.
