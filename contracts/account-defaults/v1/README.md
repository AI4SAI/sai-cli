# account.defaults/v1

`GET /v1/account/cli/defaults?site_id=site-a`, authorized by the user's Identity
resource token with `sai.compute.read` and current Portal account admission.

`scope=user` and `default_account_id` describe the global saved preference.
Null means no explicit choice. `choices` lists currently eligible accounts at
the selected site; `effective_account_id` is that site's desired default, not
an observed Slurm value. Another active site can still prevent a global change.

`deliveries` exposes only the user's current projection generation for each
active site. `pending` includes an older intent still executing before catch-up.
`applied` requires a succeeded current generation whose target matches the
desired default and has a matching accepted execution checkpoint. `applied_at`
is its recorded completion time, not a fresh native observation. `failed`,
`unavailable` and `not_requested` must not be rendered as successful application.

No raw native rows, errors, task payloads, filesystem paths or credentials enter
this DTO. There are at most 500 choices and 64 deliveries; excess data fails
explicitly. Additive unknown fields are ignored by the CLI, which validates
scope, types, safe text and receipt consistency before output.
