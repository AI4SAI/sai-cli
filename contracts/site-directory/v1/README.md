# site.directory/v1

Paired CLI PR7 and Portal PR308 are merged. Production activation remains
a separate release and ordinary-user acceptance step.

`sai sites` calls `GET /v1/account/cli/sites` with the existing Identity
`sai.compute.read` scope and current account admission. It needs no selected
site, cluster, shell access, native client or site-read capability.

Portal projects only `site_id` and `display_name` from the same enabled site
metadata used by its workspace site chooser. These are published names, not a
list of the caller's site permissions, resource availability, SSH destinations
or gateway origins. Discovery grants no further read or management authority.
The user explicitly passes `--site` to a later command; discovery never saves
or changes that choice, billing account or shell directory.

`limit` is 1–100 (default 50). Rows are sorted by exact site ID. `cursor` is the
previous page's `next_cursor`, an exclusive site-ID lower bound; it is valid
if the previous row was removed or disabled. Pages are current observations,
not a frozen snapshot. `count`, `has_more` and `next_cursor` describe this page.
Unknown and duplicate query parameters fail. Disabled entries and operational
metadata are excluded; unavailable or invalid source data is not an empty page.

Only JSON response allowlist fields are part of the contract. Subsequent
commands recheck their own membership, site, file, compute or billing policy.
This adapter introduces no directory registry, cache, route discovery or writer.
