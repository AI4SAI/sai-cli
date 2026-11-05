# Historical Slurm patch prototypes

These sources are retained for traceability and upstream investigation. They are
not supported deployment artifacts. Current SAI integration uses unmodified
upstream Slurm through its standard commands and Lua extension interface.

Any proposed upstream source change requires an independently useful, general
solution, upstream-compatible tests and explicit maintainer authorization.
The earlier implementation notes below describe the retired prototypes only.

# Slurm controller patches

`slurm-26.05.1-preserve-hold.patch` targets the upstream
[`slurm-26-05-1-1`](https://github.com/SchedMD/slurm/tree/slurm-26-05-1-1)
version of `src/slurmctld/acct_policy.c`. The SAI change preserves an existing
user/admin hold while validating a pending job's updated accounting policy.

`slurm-26.05.1-compute-reason.patch` adds diagnostics to the same version's
`acct_policy.c`, `acct_policy.h` and `proc_req.c`. It preserves scheduler decisions
and return codes. The existing account-limit writer must publish a managed
Comment prefix with the matching `GrpJobs=0` limit and remove that prefix when
the restriction is cleared. The four recognized prefixes are:

```text
[sai.compute-gate/v1:arrears]
[sai.compute-gate/v1:severe_arrears]
[sai.compute-gate/v1:no_compute_funding]
[sai.compute-gate/v1:admin_blocked]
```

The prefix must start the Comment and end at the string boundary or a space.
An operator's note may follow the space; it is never copied to job output.
Only the native branch that selects `AssocGrpJobsLimit`, on the actual blocking
association with `GrpJobs=0`, adds this bounded description:

```text
Arrears: example-account
```

The four fixed labels are `Arrears`, `Severe arrears`, `No compute funds` and
`Admin disabled`. Native text output displays this short description directly;
the internal Comment marker stays out of job descriptions and user warnings.
The original `state_reason` remains unchanged. Native JSON already exposes the
diagnostic as `state_description`; clients must validate both fields and render
the recognized reason. Account names outside the diagnostic's existing client
contract, `[A-Za-z0-9][A-Za-z0-9_.+-]{0,127}`, retain the ordinary native reason.
No account, job or submission is rejected by that diagnostic check.

Native QoS precedence and reservation handling run before this branch. The patch
does not infer funding from a balance, query another service or database, modify
Lua, or add a per-user association projection. It adds fixed Chinese/English warnings
to the existing batch and resource-allocation responses; those cover ordinary
`sbatch`, `salloc` and allocation-creating `srun`. The two heterogeneous submission
paths retain their native rejection when the pre-select accounting check fails,
and append the same warning to that error. An existing allocation's `srun` steps
do not perform a new account submission check. Unknown state emits no warning;
warnings never assert acceptance. Federation behavior is unchanged.

The next native scheduling evaluation clears or replaces the description after
a cause or limit changes. Diagnostic changes also advance the native job-update
timestamp, including a new reason with the same numeric limit. Publication
readback is not synchronous refresh of every queued job. Native holds, other
pending reasons, arrays and restart state retain their existing lifecycle.

`slurm-26.05.1-literal-association-comment.patch` separately supplies the
publisher's lossless native write path. The exact `CommentLiteral=` assignment
copies the value after `=` unchanged; it accepts no abbreviated name or `+=`/`-=`
operator. Pass the complete assignment as one argument without adding shell
quoting or SQL escaping to its value. Literal quotes, case, whitespace,
backslashes and an empty value are preserved. The existing `Comment=` option
continues using its original parser.

Association Comment decoding explicitly uses Slurm's bounded literal string
unpacker. The usual DBD string decoder already escapes single quotes and
backslashes for SQL; using it here would also put those escapes in the record
sent to the controller. The MySQL plugin instead escapes only its temporary SQL
representation with Slurm's existing string helper, preserving the original
association and controller-cache value.

This patch requires the patched `sacctmgr` client, the association decoder
linked into `slurmdbd`, and its patched MySQL accounting plugin. Activate the
publisher only after all are installed and a native
write/readback preserves the original text. Do not use the literal client with
an unpaired DBD decoder/plugin, or pre-escape values in the publisher.

The original file identifies Copyright (C) 2008 Lawrence Livermore National
Security, produced at Lawrence Livermore National Laboratory, written by
Morris Jette, CODE-OCEC-09-009. It is part of Slurm, under GNU GPL version 2 or
later with the OpenSSL exception stated in that file. Keep these upstream terms
when distributing or applying this patch; no SchedMD/LLNL endorsement is implied.
`proc_req.c` also identifies SchedMD LLC and The Regents of the University of
California as copyright holders. These SAI patches retain their upstream terms.

The following notices are copied verbatim from that upstream tag:

- [COPYING](COPYING): Slurm's license agreement and GNU GPL text.
- [DISCLAIMER](DISCLAIMER): upstream notices, acknowledgments and disclaimer.

| Upstream input | SHA-256 |
| --- | --- |
| `src/slurmctld/acct_policy.c` | `b0079e887a02ad9c466175d3661b6497c64c2ce264ad1d76a1cc3f52a8bf4be5` |
| `src/slurmctld/acct_policy.h` | `10b37cf9193b2749f64c87eb51b43e368bc0755c974836f6361806185107abb9` |
| `src/slurmctld/proc_req.c` | `004fe165c08781893aebd0ed832578fd255ca299449e8f04cba01f3c0d3985ca` |
| `src/sacctmgr/association_functions.c` | `e4e581422b8f6ff68de410e1c26eb9fa7a9c3ecb6136b8442d5e76a0024b1dca` |
| `src/common/slurmdb_pack.c` | `6692360c18761bcbdccdf98290de297d0ea68001332498d869cf33afc60b3d58` |
| `src/plugins/accounting_storage/mysql/accounting_storage_mysql.c` | `e4d51824d404b240fcabc085ae63083c27a4cb3548d8d7372c418d62a3b53166` |
| `COPYING` | `0ce020db66ca1a1497b7e5ca36630b9c0987132e779ed97eb7dd14771b285639` |
| `DISCLAIMER` | `40cd4123ce44cb922a6a3db84327c58afb66fa92e763d61672b5352bc703d357` |

Apply the hold-preservation patch and then the compute-reason patch to these
matched inputs. Check each patch with `git apply --check` before applying it.
Retain the hold-preservation patch until the deployed upstream version includes
its fix; remove the compute diagnostic patch when an upstream equivalent serves
the same consumers. The literal-comment patch touches separate files and can be
applied independently; retire it when an upstream lossless assignment and matching
backend escaping replace it. These patches are source candidates: source applicability
and local parser checks do not establish a built or deployed controller.

Before deployment, use an isolated controller and accounting database with
synthetic account/user/partition associations to verify reason changes with an
unchanged limit, recovery, preserved operator notes, finite QoS overrides,
reservations, arrays, native holds, rejected/accepted submission responses and
controller restart. The literal path must round-trip mixed case, leading/trailing
whitespace, both quote types, backslashes, Unicode and empty text through the
database and controller cache without double escaping. Pair the controller with
the cause publisher and client
reader, and retain package-level rollback. The cause is a native account
restriction diagnostic, not authorization or a final billing fact. Native
coordinators can modify association comments within their existing authority;
the marker is not a signed statement of business provenance.

This directory is not part of the Python distributions. The full repository
retains the operator patch and upstream notices together. See
[the controller policy guide](../../../docs/job-submit-policy.md) for its
version, validation and removal boundary.
