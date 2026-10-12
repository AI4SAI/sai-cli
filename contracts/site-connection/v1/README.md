# site.connection/v1

`GET /v1/account/cli/sites/{site_id}/connection` describes one explicitly selected,
published site. It accepts a registered Identity resource token and rechecks
current account admission. It grants no job, storage, billing or management
permission; each subsequent operation retains its existing scope and policy.
No extra resource-read scope is needed to read this published connection metadata.

Portal owns `cluster_id` and the explicitly configured `site_read_public_url` in
its existing site configuration. The response allowlists the latter as
`site_read_base_url`. A null origin means that no client endpoint is published;
the internal relay URL, site-agent credentials and operational settings are
never substituted or exposed. Separate and shared ingress use the same origin
contract. Metadata never chooses a different site or probes a gateway.

The CLI resolves missing connection facts for capability-based native job and
quota reads. Running-cost reads may resolve a missing cluster while retaining
their central route. Complete existing profiles need no discovery request.
Explicit cluster constraints must match; an explicit protected read origin is
preserved. Local native commands and central account/catalog reads do not use
this endpoint. Existing complete central-relay profiles keep their JSON contract.

Origins are bounded HTTPS origins without userinfo, paths, query, fragment or
terminal controls. Loopback HTTP supports local tests; HTTPS discovery cannot
select an HTTP endpoint. Identity Bearer remains at Portal, and the chosen
gateway receives only its independently acquired narrow capability. Redirects,
failed discovery and gateway errors never trigger another site or transport.

Resolution is in memory for one command invocation; it does not rewrite TOML,
persist a route cache, renew permissions or add a discovery service. A fresh
portable invocation needs the central metadata endpoint when configuration is
incomplete. A fully configured profile retains its existing cached-capability
behavior. Responses use `Cache-Control: private, no-store`.

Unknown or disabled sites return `site_connection_not_found`. Missing runtime
configuration returns `site_connection_unavailable`; missing public origin is
reported separately by operations that need a gateway. Older servers without
this endpoint cannot complete discovery. Client and server activation must be
paired; source support alone is not deployment or independent-user acceptance.
