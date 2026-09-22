# Shared CLI deployment

The release has one immutable shared runtime archive. The small integration
Debian package is only for an existing package-owned login-node entrypoint;
compute nodes do not install it. `scripts/build_login_node_deb.py` builds both from
committed source. The runtime is published once in the existing platform tree;
node packages never write files into the shared filesystem.

```text
/opt/sai/cli/releases/<version>/bin/sai
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

For the login panel and complete workbench, add `--with-tui`. The publisher
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
managed entrypoint. The node package contains `/usr/bin/sai`, a generic example
and its manifest under `/usr/share/sai-cli`. It contains no runtime code, token,
key, site agent, scheduler reader or Portal ORM. Never run a package installer on
multiple nodes against the same shared runtime files.

## Configuration and authentication

`/etc/sai-cli/config.toml` remains a root-owned, non-secret external input. It is
not overwritten by the package. Its ownership and permissions are validated by
the client because it selects credential destinations.

The managed entrypoint forces production mode, Identity authentication and the
capability-bound Portal routes. Python runs isolated with user site-packages and
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

Remove obsolete runtime copies, temporary install trees and superseded wrappers
after their consumers have migrated. Keep release evidence outside this repo.
