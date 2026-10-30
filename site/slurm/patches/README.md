# Slurm controller patch provenance

`slurm-26.05.1-operator-suspend.patch` makes new job suspension an operator
action by reusing Slurm's `validate_operator` check at the `REQUEST_SUSPEND`
entrypoint. Ordinary users can still resume and cancel their own jobs. Pending
hold/release and scheduler preemption keep their native behavior. This site
policy prevents unprivileged indefinite retention of memory and GRES while
Slurm's active-runtime accounting clock is stopped; it adds no billing rule.

The patch targets upstream `slurm-26-05-1-1` `src/slurmctld/proc_req.c`
(SHA-256 `004fe165c08781893aebd0ed832578fd255ca299449e8f04cba01f3c0d3985ca`).
It is a SAI site-policy modification, under the upstream GPL version 2 or later
with its OpenSSL exception and notices retained below. It is not an upstream
policy recommendation. Revalidate this gate and native owner/operator behavior
at each controller upgrade; remove it if the site adopts equivalent upstream
authorization or a different resource-retention accounting policy.

`slurm-26.05.1-preserve-hold.patch` targets the upstream
[`slurm-26-05-1-1`](https://github.com/SchedMD/slurm/tree/slurm-26-05-1-1)
version of `src/slurmctld/acct_policy.c`. The SAI change preserves an existing
user/admin hold while validating a pending job's updated accounting policy.

The original file identifies Copyright (C) 2008 Lawrence Livermore National
Security, produced at Lawrence Livermore National Laboratory, written by
Morris Jette, CODE-OCEC-09-009. It is part of Slurm, under GNU GPL version 2 or
later with the OpenSSL exception stated in that file. Keep these upstream terms
when distributing or applying this patch; no SchedMD/LLNL endorsement is implied.

The following notices are copied verbatim from that upstream tag:

- [COPYING](COPYING): Slurm's license agreement and GNU GPL text.
- [DISCLAIMER](DISCLAIMER): upstream notices, acknowledgments and disclaimer.

| Upstream input | SHA-256 |
| --- | --- |
| `src/slurmctld/acct_policy.c` | `b0079e887a02ad9c466175d3661b6497c64c2ce264ad1d76a1cc3f52a8bf4be5` |
| `COPYING` | `0ce020db66ca1a1497b7e5ca36630b9c0987132e779ed97eb7dd14771b285639` |
| `DISCLAIMER` | `40cd4123ce44cb922a6a3db84327c58afb66fa92e763d61672b5352bc703d357` |

This directory is not part of the Python distributions. The full repository
retains the operator patch and upstream notices together. See
[the controller policy guide](../../../docs/job-submit-policy.md) for its
version, validation and removal boundary.
