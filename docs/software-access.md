# Software module access

Status: candidate; deployment and real-user acceptance are separate gates.

Commercial-software authorization remains a Portal fact. Active grant sources
are combined there and the existing revision-bound site task applies one
software-group membership. Native permissions protect installed software.

The Portal repository's package-owned `sai_shared/software_access.toml` is the
single reviewed software/group definition for center and site code. An operator
runs `python -m sai_shared.software_access` at the site publication point to
resolve its native groups and produce `software-access.tsv`. The export is static
installation metadata, not user permission data or a renewable credential.
It contains no member lists, contract evidence or license-server credentials.

The UTF-8 contract is a header `# sai-software-access/v1`, followed by one
tab-separated `software_key`, positive decimal GID and display-name row per
software. Keys are lowercase identifiers, GIDs exclude zero and the reserved
unsigned maximum, and labels are bounded, nonempty text without controls.
Unknown or duplicate keys, invalid records and a missing definition fail closed.
Different sites resolve their own GIDs; numbers are never compiled into the
shared checker.

Publish `site/modules/software_access.tcl` and the generated TSV together under
the existing shared modules root, outside MODULEPATH. A Tcl modulefile calls:

```tcl
source -encoding utf-8 /opt/modules/site/software-access/current/software_access.tcl
sai_require_software_access example
```

Explicit UTF-8 source encoding also works with Lmod's Tcl translation locale.
Put this before dependencies and environment changes. The helper checks only
load mode, using `/usr/bin/id -G` without a username. This reads the current
process's numeric groups; it performs no Portal, directory-service, OAuth or
license-server request. Success is silent. Failure tells the user to open the
console or reconnect after access was enabled. Show/help/spider and unload do
not check membership. The same helper accepts every configured software key.

The helper belongs to the shared module environment and the sdist, not the CLI
wheel. A normal shared publication does not install anything on compute nodes,
alter mounts or require a new `sai` command. User environment variables are not
permission evidence, and there is no root exception or per-session allow marker.
Old processes retain their group credentials: refreshing NSS does not update an
existing shell or stop an already-running application.

## Acceptance and rollout

Preserve existing group names and restricted software-directory permissions.
Inventory and checksum the exact modulefiles first. Stage one versioned helper
and data directory, test explicit candidate module paths as ordinary users, and
atomically publish the reviewed modulefiles and release pointer with backups.
Preserve all existing scientific environment settings. Refresh the existing
Lmod discovery cache through its established publication command when required.

Validate both software families, unknown/no-group rejection, primary and
supplementary groups, forged environment values, read-only module operations,
grant-source union and revoke semantics, old/new sessions and direct file
access. A third configured test software must use the same code. Include a
representative compute-node read through the existing mount. Local Tcl tests do
not prove the real Portal/FreeIPA task chain, installed Lmod or NFS enforcement.
