# Software module access

Status: implemented; deployment acceptance is recorded separately below.

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

Publish `site/modules/software_access.tcl` and the generated TSV together in an
immutable release under the existing shared modules root, outside MODULEPATH.
Each Tcl modulefile calls the matching helper with its software key and the
canonical protected root of its own installation. For example:

```tcl
source -encoding utf-8 /opt/modules/site/software-access/releases/RELEASE/software_access.tcl
sai_require_software_access example /opt/apps/example
```

Explicit UTF-8 source encoding also works with Lmod's Tcl translation locale.
Put this before dependencies and environment changes. At publication, verify that
the root is the directory used by this module, its owning group matches the GID
exported for this key, and its mode and ACL grant read and search to the software
group and the installation owner. Check for any other grants. A public parent
or the mode of a binary below the protected root cannot establish that boundary.
Use a fixed modulefile argument. User input and environment variables cannot
select the directory.

On load, the helper validates the registered key and directory, then asks the
kernel whether the current process can read and search the directory. This
works when a user namespace cannot display the numeric software GID. Success is
silent. Show, help, spider and unload skip the preflight. No per-load Portal,
NSS, OAuth or licence-server request is required.

The helper belongs to the shared module environment and the sdist, not the CLI
wheel. A normal shared publication does not install anything on compute nodes,
alter mounts or require a new `sai` command. An installation owner or an
administrator who already has native access passes the same check. Module
loading reports current file access; Portal remains the source of commercial
authorization. There is no separate root exception or per-session allow marker.
Old processes retain their group credentials: refreshing NSS does not update an
existing shell or stop an already-running application.

The existing site identity-refresh task handles effective permission changes.
Refresh the changed user's SSSD entry on identity consumers; NFS servers using
`manage-gids` also need their native server group cache invalidated. That NFS
invalidation is server-wide. Missing cache entries are normal for new users;
actual refresh failures must prevent a successful consumption receipt. Verify
both membership and file access before declaring the change effective.
Refresh traffic scales with permission changes and target count, not daily
active users or module loads. Bulk changes require bounded delivery; this is
not a claim of measured peak capacity.

Module metadata must remain readable without access to the installation. If a
module sources an environment script from a restricted directory, use the native
Tcl load/remove modes around that operation; `show`, `help` and `spider` need only
the module's public metadata. This applies to every such environment script and
does not add a software-specific authorization rule.

## Acceptance and rollout

Preserve existing group names and restricted software-directory permissions.
Inventory and checksum the exact modulefiles first. Stage the versioned helper
and TSV before changing any modulefile. Test explicit candidate paths as
ordinary users. Replace the helper reference and both arguments together in
each modulefile by an atomic rename, retaining its original bytes and metadata.
Rollback restores the complete old modulefile while its original helper remains
available. Preserve all existing scientific environment settings. Refresh the existing
Lmod discovery cache through its established publication command when required.

The nine inventoried modulefiles use this migration path. Before their migration
they call the one-argument helper through `current`; the replacements reference
the two-argument release directly. Leave `current` on its previous release so
older and in-flight calls can finish, including during rollback. A custom
one-argument caller still has the old group-number behavior. Retire the old
binding only after its consumers, in-flight loads and rollback requirement end.

Validate both software families, unknown/no-group rejection, primary and
supplementary groups, forged environment values, read-only module operations,
grant-source union and revoke semantics, old/new sessions and direct file
access. A third configured test software must use the same code. Include a
representative compute-node read through the existing mount. Local Tcl tests do
not prove the real Portal/FreeIPA task chain, installed Lmod or NFS enforcement.

Bounded site acceptance completed with both software families: shared module
and file access from a login node and a representative compute node, denial
without membership, source-union retention and final-source revocation through
Portal tasks and five identity consumers. An existing shell retained its GIDs
after revocation while new file opens were denied by NFS. This does not claim
termination of running programs, every-site coverage or a load-test result.
Private operations evidence and rollback artifacts are kept outside this repo.
