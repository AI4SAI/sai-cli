# CLI operation description v1

`sai describe` emits `cli.describe/v1` without loading configuration, credentials,
optional UI packages or native/remote providers. It describes this installed
client's operations, not the caller's current authorization or the site's
availability. `authorization_checked` is always false.

- No command path: compact operation catalogue.
- A group, such as `sai describe jobs`: catalogue limited to that group.
- An exact command, such as `sai describe account set-default`: one operation,
  including its actual parser parameters, scope prerequisites and readback.
- `--format table`: a concise human rendering. JSON is the default.
- Unknown paths fail with exit 2 and `command_not_found`, without echoing supplied
  path text or attempting another command. Values are not part of the path.

The catalogue derives command names and summaries from the existing argparse
tree. The same registration carries source, effect and protocol prerequisites;
there is no second command registry or new execution API. A new leaf must declare
its metadata; discovery never guesses that an unclassified command is a read.

`parameters` describes syntax: destination name, accepted flags (empty for a
positional), scalar type, arity (`0`, `1`, `?`, `*`, `+`), requiredness, fixed
choices, help and parser default. Null defaults do not resolve a profile or
mean the API accepts null; existing configuration precedence and domain
validators still apply. Exclusive selector groups are preserved. Native commands
omit remote connection options. Commands which reject cluster/site selectors do
not advertise them. `site_option` means a site selector is accepted;
`site_required` means an effective site must be configured or supplied. Optional
authentication/TUI site selectors remain distinct from a global write which
rejects site selection. On managed hosts all connection overrides remain forbidden;
this offline description does not inspect or weaken that installed policy.

`required_scopes` is a minimum prerequisite, never a grant. Conditional scope or
native-executable requirements are separately stated. Current account admission,
shell policy, membership validity, site access, exact object permission and
file/billing checks remain server-owned. Local Unix visibility is independent.
Declared effects exclude incidental authorization audit and protected cache
refresh; `local_file_write`, `business_write` and `session_write` distinguish
output downloads, Portal mutations and Identity/credential operations. An
interactive terminal or browser-consent operation is labeled explicitly.
`effect` describes default behavior. An optional mutation such as
`invitations accept --apply` declares `business_write` and its extra scope in
`conditional_requirements`; without that flag the command remains a read.

For `account set-default`, `readback` is `account defaults`: read valid choices
and the saved value, submit that expectation with a stable request key, then read
current preference and site receipts. `accepted` is not `applied`. An uncertain
write must reuse the same intent/key, never automatically create another request.
Discovery exposes no additional mutation, generic HTTP proxy or privilege.

Connection options remain valid before or after the leaf of operations that use
them. Optional values, paths and names stay data; callers should execute an argv
array and must never put credentials in argv. No live addresses, current account
IDs, tokens or saved profile values are part of the description.
