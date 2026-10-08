# Shared CLI deployment

This is the cluster installation role, not the only supported product target.
User devices and dedicated isolated user VMs install the same CLI independently
with per-user configuration/credentials. They do not require this NFS tree or a
Pilot runtime. The package supports HTTP reads and explicit local job queries;
other native helper integration and Portal management remain planned.

The release has one immutable shared runtime archive. The small integration
Debian package is only for an existing package-owned login-node entrypoint;
compute nodes do not install it. `scripts/build_login_node_deb.py` builds both from
committed source. The runtime is published once in the existing platform tree;
node packages never write files into the shared filesystem.

```text
/opt/sai/cli/releases/<version>/bin/sai
/opt/sai/cli/releases/<version>/bin/stat_job
/opt/sai/cli/releases/<version>/bin/stat_job_all
/opt/sai/cli/releases/<version>/bin/stat_gpu
/opt/sai/cli/releases/<version>/bin/stat_cpu
/opt/sai/cli/releases/<version>/site-packages/
/opt/sai/cli/current -> releases/<version>
/opt/sai/bin/sai -> ../cli/current/bin/sai
/usr/bin/sai -> /opt/sai/bin/sai
```

The shared platform root replaces the old environment/configuration/example/
site-Slurm mounts as described in [the layout contract](platform-runtime-layout.md).
It is not a new per-command mount. Each node supplies Python 3.11 or later.

## Build and provenance

```bash
.venv/bin/python scripts/build_login_node_deb.py --output-dir dist/deb
```

For the optional formatted login panel, add `--with-tui`. The publisher
bundles the hash-pinned pure-Python wheels from `packaging/login-node/tui-requirements.txt`
into that one shared release and records each wheel digest in the manifest.
JSON/plain-text users retain the dependency-free base package; consumers never
run pip or install a local TUI copy. This option changes the shared archive,
not the node integration package's filesystem ownership.

Formal builds require a clean HEAD reachable from `origin/main`. Build inputs
come from `git archive`, so ignored files and uncommitted work never enter the
release. The standard isolated PEP 517 backend builds the wheel. Timestamps,
archive ownership and permissions are deterministic; the manifest records the
full Git SHA, source/wheel/runtime digests and node-package digest.

The runtime tar contains only `cli/releases/<version>` with the client and its
managed entrypoint and thin native job/resource wrappers. The node package contains `/usr/bin/sai`, a generic example
and its manifest under `/usr/share/sai-cli`. It contains no runtime code, token,
key, site agent, scheduler reader or Portal ORM. Never run a package installer on
multiple nodes against the same shared runtime files.

## Configuration and authentication

`/opt/sai/cli/config.toml` is a root-owned, non-secret shared input.
Publish it once with the managed site settings; compute nodes need no config copy. It is
not overwritten by the package. Its ownership and permissions are validated by
the client because it selects credential destinations.

For remote commands, the managed entrypoint forces production mode, Identity
authentication and capability-bound routes. `jobs local` dispatches before API
configuration/authentication, using the current user's native Slurm environment.
Python runs isolated with user site-packages and
bytecode writes disabled. Browser device login and protected per-user rotating
refresh credentials retain their existing contract; moving program files does
not migrate or invalidate those sessions.

## Publish, canary and switch

1. Verify the manifest and extract the exact version on the app publisher with
   `umask 022`. Runtime directories/executables are `0755`, regular files `0644`.
   Only the publisher writes; consumers use the shared files.
2. Check Python and mount availability on representative login/compute nodes.
   Run the explicit versioned entrypoint as an ordinary user before activation.
3. Atomically select `cli/current`. Ensure `/opt/sai/bin/sai` resolves to the
   selected release. Update an existing login-node integration package only when
   its stable entrypoint needs migration. This is not a compute-node release step.
4. Verify the manifest, executable resolution, authenticated job read and
   non-final cost read with an existing authorized device session. `--version`
   alone does not prove API or authentication behavior.

## Migration and rollback

Upgrading the old node-local `sai-cli` package removes its package-owned
`/opt/sai-cli` files and replaces the entrypoint with the shared link. Do not
manually delete dpkg-owned files or leave a second selected implementation.

Keep the previous shared version and node package until consuming-layer checks
pass. Shared rollback atomically restores `cli/current`; the node package is
restored with its recorded Debian artifact if integration also changed. The
external config and user credential caches are independent of either action.

Existing `stat_job` and `stat_job_all` need one reviewed shared-entry migration:
inventory/checksum the old scripts and their callers, retain exact rollback
copies, canary the explicit new wrappers as an ordinary user, then atomically
replace those shared entries with links to `../cli/current/bin/<name>` on the
publisher. Existing shell aliases remain intact. Both wrappers call the same
versioned CLI; the all-jobs wrapper adds the existing `-u '*'` behavior. No node
package, mount or login-profile change is needed. Normal subsequent releases
follow `cli/current`. A rollback to a release predating these wrappers must
restore the saved legacy entries as part of the same bounded rollback.

The legacy `sqa`/`ja` aliases also need the one-time
[`native_job_aliases.patch`](../site/shell/native_job_aliases.patch) migration.
They select `_SAI_LOGIN_ACCOUNT`, already resolved by the native login-context
hook, rather than the unrelated Unix `GROUP_NAME`. Keep the Unix group variable
for its existing consumers. Missing applied context is a clear error, never an
all-job query or a guessed account. Apply the patch to a checksum-verified copy
of the shared profile, check shell syntax, canary it, then replace that one
profile atomically on the publisher. Keep its complete rollback copy. New login
shells load the new aliases; existing shells retain their definitions until
reloaded. Restore the profile before a paired CLI rollback that checks its hash.

Remove obsolete runtime copies, temporary install trees and superseded wrappers
after their consumers have migrated. Keep release evidence outside this repo.

GPU/CPU helpers follow the same shared-entry migration: checksum and retain the
existing scripts, canary the explicit `bin/stat_gpu`/`bin/stat_cpu` wrappers,
then link the two shared entries to `cli/current/bin`. Preserve positional
partition selection. Default output becomes a compact partition overview;
selecting a partition or `--details` shows node observations. This changes neither
the `gpu`/`cpu` aliases nor their native permission boundary. Rollback to a version
without these wrappers restores their saved scripts before changing `cli/current`.
