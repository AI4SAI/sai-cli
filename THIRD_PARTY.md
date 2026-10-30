# Source provenance and third-party components

First-party SAI client code, the shared native projection and official Agent
guidance use Apache-2.0. Upstream components retain their own licenses and
notices; no upstream endorsement is implied.

## Client and shared projection

The base Python wheel contains the SAI client and its official Agent skill,
with no third-party runtime dependency. `src/sai_native_slurm.py` is an exact
export of the SAI Portal native projection. Its originating path, revision and
digest are recorded in [the source manifest](contracts/native-slurm-source.json).
The topology reader in `src/sai_native_topology.py` is likewise an exact export;
its source and digest are recorded in
[the topology source manifest](contracts/native-topology-source.json).
Both shared exports are included in the first-party Apache-2.0 license.
Portal services, databases and their other code are not part of this client.

Slurm and Lustre commands are external native programs. The wheel includes
neither their source nor binaries. Local queries call installed native tools
under the user's Unix authority; they do not redistribute an HPC runtime.

## Optional terminal dependencies

The optional UI uses the pinned distributions below. A normal `pip` install
resolves separate packages. The shared cluster runtime bundles those same
pure-Python wheels and retains their original `dist-info` license files.
Hashes are owned by [the existing dependency lock](packaging/login-node/tui-requirements.txt).

| Distribution | Version | Upstream license |
| --- | --- | --- |
| Textual | 8.2.8 | MIT |
| Rich | 15.0.0 | MIT |
| linkify-it-py | 2.2.0 | MIT |
| markdown-it-py | 4.2.0 | MIT; includes the original markdown-it notice |
| mdit-py-plugins | 0.6.1 | MIT |
| mdurl | 0.1.2 | MIT |
| platformdirs | 4.11.12 | MIT |
| Pygments | 2.21.0 | BSD-2-Clause |
| typing_extensions | 4.16.0 | PSF-2.0 |

This table describes the inspected pinned artifacts, not future dependency
versions. Keep their complete notices when rebundling; the table is not a
replacement for upstream license text. Development tools are not bundled in
the client runtime.

## Separate native scheduler patches

`site/slurm/patches/slurm-26.05.1-preserve-hold.patch` modifies Slurm's
`src/slurmctld/acct_policy.c`; `slurm-26.05.1-operator-suspend.patch` in the
same directory modifies `src/slurmctld/proc_req.c`. These upstream files are GPL
version 2 or later, with the upstream OpenSSL exception and notices. Their terms are kept separately
in [the repository's patch directory](https://github.com/AI4SAI/sai-cli/tree/main/site/slurm/patches).

The scheduler patches are repository/operator artifacts. They are excluded from the
Python wheel and source distribution; obtain them and their notices from the full
repository when building a patched Slurm. The first-party client license does
not relabel these upstream-derived patches. The SAI Lua, shell and Tcl site
artifacts retain their separately documented operating roles.
