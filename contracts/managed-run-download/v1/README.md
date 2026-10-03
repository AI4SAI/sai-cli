# Managed output download

Status: paired candidate, not a production rollout. This contract completes file
retrieval independently of text preview or a Pilot Session. Binary files do not
pass through a text decoder, the Center byte stream, or a browser Blob buffer.

## Authorization and response

Browser and CLI POST to their existing `/v1/account/compute/runs` or
`/v1/compute/cli/runs` prefix, then
`/{run_ref}/artifacts/{artifact_ref}/download`. The JSON object contains only
`workspace_key`, `site_id`, optional nullable `artifact_cursor` and `version`.
The list cursor identifies the selected 100-item page, not its next page.
No query parameters, filename, native user or path overrides are accepted.

The owner reuses current Run READ, separate applied file READ, the frozen mount
lineage, declared output roots and selected artifact. A small native probe
establishes the current full file version and exact size. Passing `version`
requires that version; a change is 409, not a silently substituted file.
Missing files are 404, file READ denial is 403, and unavailable configuration or
sources are 503. It does not start a model, submit a job or grant file writes.

`compute.run-artifact-download/v1` echoes the four scope/object references and
returns a safe basename, size, version, controlled `download_url`, short opaque
`capability`, integer Unix `expires_at`/`transfer_until`, and
`range_max_bytes=8388608`. Consumers validate the context and selected basename.
The endpoint is HTTPS, exactly `/v1/site-files/artifacts/download`, without URL
credentials, query or fragment; local test servers may use loopback HTTP.
The site origin comes from protected deployment configuration, never user input.
Capabilities are credentials: no argv, JSON command output, URL, storage or logs.

The signed inner `artifact-download-grant.v1` binds the subject, site/cluster,
Run/artifact, native owner and scheduler reference, exact version and size, and
absolute `transfer_until`. It contains a digest identifying an existing protected
site root, its workspace-relative path and the artifact-relative path. The native
probe derives the root from the same trusted FD walk; the Center verifies that
the relative locator reconstructs its authorized root. The site resolves the
digest only against its existing protected roots, then opens the workspace and
file in two separate FD walks. It does not infer a path from account names or
query a new registry. The signed token is decodable, not encrypted; authorized
relative directory/file names are an intentional contract expansion. Absolute
native roots and general site credentials never enter the client response.

## Native transfer

The existing site execution service owns the narrow capability-only route. The
separate low-privilege jobs/quota gateway acquires no file or sudo permissions.
An ingress exposes only this exact route and strips ambient Identity credentials
and cookies; it must not proxy the internal site-agent API generally.
When the existing TLS listener is the jobs gateway, its optional exact streaming
relay targets only a protected loopback URL on the same site. Verification,
file permissions and native access remain in the execution-service file owner.
The relay receives no internal shared secret or new filesystem permissions; no
new listener or file service is required.

- GET uses only `X-SAI-Capability`. An explicit single `Range: bytes=start-end`
  requires `If-Match: "version"`, is at most 8 MiB, and returns 206 with exact
  Content-Range, Content-Length and ETag. A whole-file or empty-file GET is 200.
  Multiple/open/suffix ranges are outside this initial contract.
- Browser POST is a bounded URL-encoded form containing `capability` and an
  optional 16–64 character alphanumeric/hyphen `request_id`. The request ID only
  correlates a browser error; it has no authorization meaning. No custom
  authentication header or CORS-enabled fetch is needed for native attachment.
- The service verifies the first chunk before sending response headers. It sends
  `application/octet-stream`, attachment filename/filename*, exact Content-Length,
  ETag, no-store and nosniff. Every native read uses the owner UID, no-follow file
  descriptors, the same filesystem, and before/after version checks.
- Data comes from bounded 8 MiB helper receipts and is released in 64 KiB pieces.
  Four active responses per process include blocked readers/senders. The helper's
  receipt size is checked after collection, so this is not a hard memory ceiling
  for a malfunctioning helper. Async cancellation terminates and drains its
  subprocess. Production process count and memory capacity require acceptance.
- Missing/changed files, revoked capabilities, source failure or deadline after
  headers terminate the response. Never append JSON/HTML or emit a successful
  short EOF. Bytes already accepted by the network cannot be recalled.

The short capability expiry admits new requests only. An already admitted
response can continue until the signed fixed transfer deadline, at most one hour
after issuance. Wall-clock remaining time becomes a monotonic deadline that also
cancels blocked sends. This does not lengthen ordinary job grants. The stateless
token may admit repeated requests before expiry; it is not single-use.

Each response reloads protected verification inputs at most once per second.
Published JTI/key changes stop further sending within that observation window,
plus unavoidable already-buffered bytes. Revocations must remain published until
`transfer_until`, not merely token expiry. Epoch is currently process environment;
changing it requires restarting and terminating the old worker. There is no
automatic bounded Center-membership-to-site revocation delivery promise. Without
delivery, an admitted response can run until its transfer deadline. New Center
issuance always rechecks current access.

## Save behavior and browser errors

The task page submits the form to a sandboxed iframe and retains the current task.
It never claims the browser saved the file; native progress, cancellation and
completion belong to the browser download manager. Before headers, a valid
`request_id` allows a fixed, CSP-limited error document to post
`compute.artifact-download-error/v1` with only request_id/status/code to its parent.
The parent checks the exact iframe Window, opaque origin, latest attempt and
strict shape before showing a localized error. Earlier tasks/attempts cannot
display a late refusal. No permission is inferred from this message.

CLI/TUI save to the machine running that client. A private temporary directory in
the destination filesystem holds the partial bytes. Every range and any renewed
grant must keep the initial version/size. Only complete, fsynced data is published
without replacing any existing destination. Cancellation or failure removes this
attempt's partial file. The initial release does not promise browser POST resume
or a cross-process CLI resume; a new user attempt starts again.

## Paired release gates

Install the native helper/site capability reader and public verifier inputs before
enabling Center issuance or consumer controls. Reuse the current signer and key
publication; keep independent role runtimes and current peer changes. Configure a
trusted per-site file URL and exact GET/POST TLS route with buffering, cache,
redirects and automatic upstream retries disabled. The browser CSP must permit
the selected origin for form-action/frame-src and the small error frame must not
inherit an API-wide frame-ancestors/X-Frame-Options denial. Do not weaken other
API or console framing rules. A shared origin is only an ingress choice, not an
obligation to move file bytes through Center or choose another compute site.

Tests separately establish local native reads, real TCP authorization/transfer,
consumer saving and browser behavior. They do not prove production routing,
certificate validation, service UID/mount permissions, revocation delivery or a
complete scientific computation. Firefox/Safari and longer transfers require
their own browser acceptance; Chromium success is not universal-browser proof.
