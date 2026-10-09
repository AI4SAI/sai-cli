# account.default-change/v1

`PUT /v1/account/cli/defaults`, authorized by the user's Identity resource token
with independent `sai.compute.defaults.write` and current Portal account admission.
This scope grants only this preference mutation; it implies no job, storage,
membership or financial write.

The body contains exactly `account_id` and `expected_account_id`. Both are
nullable: null requests automatic selection or expects no saved explicit choice.
The caller supplies an `Idempotency-Key` of 8-128 ASCII letters, digits, `.`,
`_`, `:` or `-`. It is an operation identifier, not a credential. There are no
query selectors; the setting is global even though sites apply it separately.

The server checks the saved value under the existing principal lock. It calls
the same writer/cooldown as browser preferences and queues the existing site
projections in that transaction. A projection failure rolls back the preference,
tasks and request reservation. The existing idempotency record stores the
allowlisted acceptance. A same-actor/key/body replay returns it without another
write, including after a later preference change. Another body or a conflicting
saved value returns 409; callers must inspect and choose a new intent explicitly.

`state=accepted` reports the original committed request, not the current saved
preference or applied site state. `site_projections` names the generations being
tracked at acceptance; an in-flight older intent can still require a catch-up
generation. Use `account.defaults/v1` for current preference and receipt status.
The CLI performs no automatic write retry. On a network failure it emits no
success; the caller can replay the original command/key/body.
