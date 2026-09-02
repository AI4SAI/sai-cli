# Login-node package and canary

Status: package run card; target install and live canary are still open.

The login-node artifact is a dedicated `sai-cli` Debian package. It is not part
of Portal's center/site roles or the identity-cache package. It contains only
the pure-Python CLI, a thin `/usr/bin/sai` launcher, a generic non-secret
configuration example, and a full-SHA manifest. It contains no Bearer token,
HMAC secret, signing key, site-agent code, Portal ORM, Slurm reader, or
scheduler mutation command.

## Build gate

Build from a clean commit already reachable from the reviewed remote `main`:

```bash
.venv/bin/python -m pytest
.venv/bin/python -m build
python3 scripts/check_public_surface.py
git diff --check
python3 scripts/build_login_node_deb.py --output-dir dist/deb
```

The builder rejects a dirty tree or a `HEAD` that is not reachable from
`origin/main`. It records the complete source commit/digest, wheel digest,
package digest, installed-file allowlist, and an explicit package-only rollback
instruction in a mode-`0600` sidecar manifest. Inspect both metadata and file
listing with `dpkg-deb -I` and `dpkg-deb -c` before transfer.

## Runtime configuration

The real `/etc/sai-cli/config.toml` is an external non-secret input. It must be
root-owned, a regular non-symlink file, and not group/world writable. The
packaged example contains `portal_base_url`, `site_read_base_url`, `site_id`,
and `cluster_id`; it does not contain credentials.

The launcher fixes `SAI_MANAGED_LOGIN_NODE=1` and the root config path, then
starts Python with `-I -P` and the versioned package path. Managed mode rejects
origin, site, cluster, cache, TLS, username/key, and HMAC overrides from argv or
environment. The only user credential accepted for the canary is a short-lived
process-local `SAI_TOKEN`; it must not enter argv, TOML, shell startup, package,
transcript, or release manifest.

## Single-user canary

Before any install, record host/user/time, `findmnt` for staging and install
paths, current entrypoint/package checksums, Python version, and the canary
user's queue/history. Extract and run the inspected package first, without
changing the global entrypoint.

Run only this read operation:

```bash
sai jobs list --scope self --limit 1 --format json
```

Acceptance requires issuer and gateway audit evidence for the named actor,
site, `jobs.list`, and the exact self filter; every returned `slurm_user` is the
canary user; and stdout/stderr contains no paths, scripts, environments, raw
scheduler fields, wallet/ledger data, token, or capability. Compare queue and
recent history before and after. Do not run `sbatch`, `srun`, `scancel`,
`sacctmgr`, account/QOS/quota changes, or configuration writes. If there is no
live job, record `jobs show` as no sample and do not submit a job to create one.

After the extracted-path check passes, install the exact inspected `.deb`, read
back package version/manifest/digest and `/usr/bin/sai --version`, then repeat
the same GET-only canary. Keep the previous package as the rollback artifact.

## Rollback and cleanup

Rollback is `dpkg -i` of the recorded previous `sai-cli` artifact, followed by
the same manifest and entrypoint readback. If this is the first install, remove
only the `sai-cli` package after checking its installed-file list. Remove
transferred packages, extraction trees, failed staging directories, and
temporary credential/cache material after evidence is captured. Retain only the
current/previous verified artifacts and the permission-protected evidence
packet.

Package build is `candidate`, target installation is `deployed`, and only the
consuming-layer user flow is `live-verified`.
