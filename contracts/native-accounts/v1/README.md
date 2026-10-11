# Native account choices

`sai account local` returns `native.accounts/v1` without Portal configuration,
OAuth or a gateway. It discovers the current Unix user's Slurm associations,
not business membership or accounts belonging to other users.

The reader shares the native association parser used by `--with-subaccounts`.
One bounded `scontrol --json ping` fixes the local cluster; one bounded
`sacctmgr -nP show assoc where cluster=... user=...` reads that UID's account
names and validates their lineage. Conflicting lineage, another cluster/user,
malformed rows, failed commands or output above 1 MiB fail the whole read.
Empty associations are a valid empty result. Native filter environment overrides
and SAI credentials are removed; the native Slurm configuration remains intact.

JSON contains `schema_version`, `source=sacctmgr`, `authority=native`, `cluster`,
`actor={user,uid}`, `observed_at` and a sorted, distinct `accounts` name list.
Lineage and raw diagnostics are not exposed. `--format table` shows the names.
`--timeout` works before or after the leaf command; remote connection/site
selectors are rejected. Reads never change the saved or applied account.

The focused TUI discovers these choices when its job selector opens, without
delaying the initial queue. Choosing an account reuses the existing native
subtree query. Every request still executes under the same UID. A native choice
does not grant Portal cost access; explicit estimates independently resolve that
account through Portal's existing authorized directory and exact job binding.

Storage is separate. The quota chooser selects an actual local directory and
uses `storage local-quota` under the same UID. It does not derive filesystem
paths or business authority from scheduler account names.
