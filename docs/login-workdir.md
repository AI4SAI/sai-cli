# Default identity login directory

Status: site artifact with local shell tests; deployment is a separate gate.

`site/shell/default_workdir.bash` is sourced by the site's existing shared
interactive profile. It is not installed by the CLI wheel and does not add a
`sai` command. The established default identity remains a Portal-owned preference
projected into Slurm; this fragment selects a directory from that applied native
fact and the account hierarchy.

The fragment queries the local Slurm cluster name, then requests only the
current Unix user's `OnlyDefaults` associations for that cluster. Slurm's
`Lineage` field carries the account ancestry even when an ordinary user cannot
read the parent account record. Both native requests have a two-second timeout.
No credentials, identity database, broad site-agent API, per-user pointer,
background worker, or additional cache is involved.

| Applied default | Canonical directory |
| --- | --- |
| Own personal account | `/home/<user>` |
| Organization account | `/org/<account>/<user>` |
| Project account with one organization parent | `/org/<parent>/<project>` |

All returned rows must match the current user and cluster and resolve to one
path. Conflicting, missing, or malformed facts fail without guessing another
identity. Slurm associations and filesystem permissions keep their existing
authorization roles; directory selection grants no access.

The automatic change happens once, only in an initial interactive login shell
that is still in Home. Root, jobs, noninteractive SSH, nested shells, and an
explicit initial directory retain their current location. Native failures or an
inaccessible target leave the current directory intact and display one bounded
diagnostic. `$HOME` is never changed.

## Release boundary

Stage a versioned candidate in an existing shared site-runtime tree, verify it
through an explicit path as an ordinary user, and switch the existing profile's
reference atomically. This feature requires no new top-level mount. A shared
profile switch affects all its consumers, even when the operator runs the
command from one login node.

Before promotion, verify actual personal, organization, and project defaults;
fresh interactive SSH; repeated sourcing; nested shells; noninteractive SSH;
missing directories; and unavailable native services. Keep the previous profile
and fragment checksums as a rollback pair. Directory layout migration and CLI
authentication remain separate ownership boundaries.

The submit hook's precedence is explicit account, canonical working-directory
account, then Slurm default. Deliver the login behavior before enabling that
account selection policy: a user left in Home would otherwise select their
personal account even with an organization default.
