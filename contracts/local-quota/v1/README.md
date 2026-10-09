# Local Lustre project quota

`sai storage local-quota [PATH]` reads the quota of the native project ID attached
to a local file or directory. Omitting PATH means the current directory. The
existing `quota [path]` shell function can delegate to this same command with
human output; Agents use its default JSON. No Portal login, gateway, directory
scan, filesystem write or privileged storage adapter is involved.

```bash
sai storage local-quota --format table
sai storage local-quota -- './directory with spaces'
sai storage local-quota --format json -- './-leading-name'
```

The caller's Unix permissions remain authoritative. Paths are not platform IDs:
spaces, punctuation, Unicode and control characters are passed as argv data.
Symlinks resolve to their target. The implementation resolves the path, reads
one `lfs project -d` attribute, then queries that ID through `lfs quota -p` with
explicit numeric/grace fields and a delimiter. It does not parse a formatted
filesystem-path column or copy the server's storage management module.
Both native calls share one deadline and have bounded output; native stderr or
an incomplete/inaccurate counter is an error, not a partial successful quota.

`--timeout` is accepted before or after the command (default 10 seconds, maximum
120). Remote connection/scope options do not select this local source. The path's
filesystem device and inode are checked again after reading; replacement fails
the read. This is an observation of the resolved project ID, not an atomic
filesystem snapshot or a guarantee that an administrator cannot later change
its assignment. No project ID, a missing path and a source failure are distinct
errors. The command never falls back to Portal or a wider subject.

## JSON and meaning

The `native.quota/v1` envelope includes `source=lfs_quota`, `authority=native`,
`coverage=filesystem_project`, effective UID/user, requested/resolved path,
host, local filesystem device major/minor, native project ID and observation
completion time. Host/device/project identify this local observation; they are
not a global durable Portal quota reference. JSON escapes native path strings
so valid filesystem bytes can round-trip through Python's filesystem encoding;
human output escapes terminal controls. No credential or raw provider diagnostic
is returned.

`used_bytes`, `used_inodes`, `block_soft_bytes`, `block_hard_bytes`, `inode_soft`
and `inode_hard` use exact decimal strings. Native KiB counters are multiplied
by 1024 without floating-point conversion. Zero limits mean unlimited, whereas
zero usage means zero. Bracketed/inaccurate, negative, scaled or malformed
counters are rejected. Native usage markers are retained separately.

Block/inode grace records preserve raw text and distinguish inactive, remaining,
expired and notify, with remaining seconds where present. These observations
describe configured native limits; they do not prove hard enforcement, physical
free disk space, business budgets or the caller's ability to write.

The counters cover all files sharing that project ID in the filesystem. They
are not necessarily this directory's subtree or this user's personal usage.
Portal's stored quota summary, authorized remote quota subjects and commercial
funding pools retain their existing owners and contracts.

The native named-field/delimiter interface is required. A successful local test
does not prove shared shell activation or every filesystem/client version.
