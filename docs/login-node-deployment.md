# Login-node package and canary

Status: production run card

The login-node artifact is a dedicated `sai-cli` Debian package. It must not be
added to Portal's center/site roles or to the identity-cache package. The
package contains only the pure-Python CLI, a thin `/usr/bin/sai` entrypoint, a
generic non-secret config example, and a full-SHA manifest. It contains no
Bearer token, HMAC secret, signing/public key, site-agent code, Portal ORM,
Slurm reader, or scheduler mutation command.

## Build gate

Formal artifacts are built only from a clean commit that is already reachable
from the reviewed remote branch:

```bash
.venv/bin/python -m pytest
.venv/bin/python -m build
python3 scripts/check_public_surface.py
git diff --check
python3 scripts/build_login_node_deb.py --output-dir dist/deb
```

The artifact and its mode-`0600` sidecar manifest record the complete source
commit, source digest, wheel digest, package digest, installed file allowlist,
and rollback shape. Inspect with `dpkg-deb -I/-c` before transfer. Do not use a
previous `dist/` wheel or a package built from a dirty tree.

The builder archives the reviewed `HEAD` into a temporary source tree before
invoking the normal isolated PEP 517 wheel build. Ignored checkout output such
as `build/` or `dist/` therefore cannot become package input. It also sets
`SOURCE_DATE_EPOCH` to the `HEAD` commit timestamp for both the wheel and
Debian archive, so repeated builds of the same commit with the same build
toolchain produce the same artifact digest. The formal path still requires an
available isolated-build dependency source (for example, the approved
internal wheelhouse for `setuptools>=69`); `--no-isolation` is only a local
test seam.

The hidden `--allow-dirty` option is reserved for tests and diagnostics. Even
there, the builder archives `HEAD` and marks the manifest as not clean; it never
mixes uncommitted checkout files into a package.

## Runtime configuration

The real `/etc/sai-cli/config.toml` is an external non-secret runtime input,
not a package payload. It is root-owned, regular, not symlinked, and not
group/world writable. Start from the packaged generic example and set only the
approved Portal origin and canonical site. Managed `/usr/bin/sai` forces:

```text
SAI_ENV=production
SAI_REQUIRE_SITE_CAPABILITY=1
PYTHONNOUSERSITE=1
```

The wrapper also passes Python's `-B` flag so importing the immutable release
tree cannot leave unowned `__pycache__` files during package installation or
normal login-node use.

The CLI therefore has no production fallback to the legacy `portal_read`
routes. The matching Portal release must already expose and enable the
capability issuer/CLI routes, use an Ed25519 key through a protected file, and
publish the matching integer policy epoch. The matching SAI Identity release
must expose the registered OIDC client and Device Authorization Grant.

Users authenticate once per login-node account with `sai auth login`; the
browser/device flow runs at SAI Identity, not Portal. The resulting rotating
refresh credential is owned by the Unix user in the protected credential cache.
No Bearer, refresh token, password, or Identity signing key is put in argv,
TOML, shell startup, the package, transcript, or release manifest. An
already-issued `SAI_TOKEN` remains a process-local emergency compatibility
input only.

## Single-user canary

Before mutation, record host/user/time, `findmnt` for the intended staging and
install paths, current `dpkg-query`/entrypoint checksums, `/usr/bin/python3`
version, and the canary user's queue/history. The first execution is made from
an explicitly extracted package path, before `dpkg -i` changes the global
entrypoint.

After the user device session exists, only run:

```bash
sai auth status --format json
sai jobs list --scope self --limit 1 --format json
```

Acceptance requires:

- issuer/read audit evidence binds the named actor, site, `jobs.list`, and
  exact self filter;
- every returned `slurm_user` is the canary user;
- no path, script, environment, raw scheduler, wallet, ledger, token, or
  capability field reaches stdout/stderr;
- queue and recent history are unchanged before/after;
- no `sbatch`, `srun`, `scancel`, `sacctmgr` write, account/QOS/quota or config
  mutation occurs;
- if there is no live job, `jobs show` is recorded as no sample and no job is
  submitted merely to create one.

After the extracted-path canary passes, install the exact inspected `.deb`,
read back package version/manifest/digest and `/usr/bin/sai --version`, then
repeat the same GET-only canary. Preserve the previous `.deb` as rollback.
If the canary device session was created only for acceptance, revoke it with
`sai auth logout` after collecting evidence; never copy its refresh credential
to another user or node.

## Rollback and cleanup

Rollback is `dpkg -i` of the recorded previous package, followed by the same
manifest/entrypoint readback. If this is the first install, rollback removes
only the `sai-cli` package after verifying its installed-file list; external
config/cache cleanup is separate and explicit.

Before closing the window, remove the transferred package, extraction tree,
temporary device-auth state or process environment, failed staging directory,
and unused tooling. Retain only the current and previous verified artifacts
plus the permission-protected transcript/evidence packet. A clean package build is
`candidate`; target install is `deployed`; only the consuming-layer user flow
is `live-verified`.
