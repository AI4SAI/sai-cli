# Public CLI connection

`GET /v1/auth/config?client=sai-cli` returns the connection metadata for this
first-party public client. It uses the existing Portal resource verifier's
configured issuer, audience and allowed clients. It does not read a database,
browser credential, user session or native site. Other client names are rejected;
missing/inconsistent server configuration returns `cli_connection_unavailable`.
Without `client`, the existing browser configuration is unchanged.

The client starts from a service URL explicitly supplied by the user. This is
the trust decision, just as with a manually supplied configuration. The response
cannot redirect the Portal URL or supply scopes, files, secrets, site selection
or site gateway addresses. Unknown additive fields are ignored. The response is
bounded to 16 KiB and requires `cli.connection/v1`, `oidc_client_id=sai-cli` and
`require_site_capability=true`. Issuer/resource fields are bounded printable
ASCII without whitespace; URLs reject userinfo, query/fragment and redirects.
HTTPS cannot discover a plain-HTTP issuer. Loopback HTTP is for local tests only.

The client reuses its standard OIDC discovery and same-origin endpoint validation
before saving. Neither metadata request carries cookies, Bearer, capabilities or
refresh credentials. Configure does not start a device grant or prove that the
client is registered in Identity; normal device authorization remains required.

`sai configure URL` creates a user-owned `0600` TOML file through atomic
non-overwriting publication. It never replaces existing profiles or credentials.
Reapplying the same connection verifies it without rewriting the file; a changed
connection requires a separate explicit `--config` path. A fresh baseline uses
`openid offline_access` plus the installed `sites` operation's compute read scope.
Additional permissions use the existing `auth login --for` consent path. Managed
shared installations reject configuration changes through this command.

The successful `cli.configured/v1` receipt contains `created`, `config_path`,
`profile`, `base_url`, `identity_issuer` and `next_commands` as argument arrays.
These are local configuration facts, not authenticated-user or site-access proof.
