# Shared platform runtime layout

Status: target ownership model, not authorization for a fleet mount migration.
Only the publisher and one login-node canary currently expose the new root.
Compute-node mount changes were rolled back; the existing shared roots remain.

## Responsibilities

The shared namespace has five durable roles:

| Shared root | Owner and contents |
| --- | --- |
| `/opt/apps` | Scientific applications and their versioned runtime dependencies. |
| `/opt/devtools` | Compilers, SDKs, build systems and development tools. |
| `/opt/modules` | Native Lmod runtime, modulefiles and software discovery. |
| `/opt/sai` | The SAI user work environment: platform commands, login integration, job examples and site execution assets. |
| `/opt/custom` | Organization-controlled applications and modulefiles, with separate write ownership. |

`sai-cli` is a platform interface for users, not a development tool. Its shared
entry belongs under `/opt/sai/bin`, with immutable client releases under
`/opt/sai/cli`. It must not acquire another top-level NFS mount of its own.

```text
/opt/sai/
  bin/sai                 stable user entry
  cli/releases/<version>/ client code and provenance
  cli/current             selected client release
  shell/                  common profile, aliases and login directory selection
  runtime/                site CPU/GPU/IB environment and mapping assets
  slurm/                  scheduler integration source and release artifacts
  examples/               user-facing job templates
```

Sharing a root does not require a single release switch for all components.
The client, shell environment and controller plugin retain their own reviewed
versions and rollback boundaries. Do not tie a client update to a scheduler
restart or make login depend on an OAuth device session.

The `/opt` parent also contains node-local vendor drivers and service packages.
Do not mount the entire parent over those installations. Making the platform root visible on all clients is an infrastructure decision,
separate from publishing code. Do not move platform tools into scientific apps
or development tools to avoid that decision, and do not modify compute-node
mounts as an implicit step in a software release.

## Shared code and local authority

- Publish shared code once through the app repository, with checksums, explicit
  public read/traverse permissions and one authorized publisher. Consumers do
  not each run a package installer against the same NFS files.
- Native Slurm binaries remain owned by the OS package. Controller plugins and
  their effective policy files are installed on the controller's local disk;
  `/opt/sai/slurm` is a release source, never the submit callback's I/O path.
- Node-specific service configuration and private credentials remain in the
  existing local configuration hierarchy. Runtime state remains in the owning
  service's local state directory. User refresh credentials stay in protected
  per-user caches, outside the shared software tree.
- Native Lmod supplies the environment-module bootstrap. Do not build another
  profile discovery framework, module cache or service to select releases.
- Portal remains the owner of default identity and QOS policy. The login
  fragment consumes the user's applied native Slurm association; the submit
  plugin consumes a reviewed local policy revision and native authorization.

## Existing paths

| Existing path | Disposition |
| --- | --- |
| `/opt/slurm/custom_rc` | Move shell entry, aliases, help and quota display to `shell`; move IB environment logic to `runtime`. Delete the mixed implementation after callers migrate. |
| `/opt/slurm/scripts` | Move release sources to `slurm`; preserve scheduler hook entrypoints until each configured caller is switched. |
| `/opt/slurm/etc` | Separate client-visible configuration from controller-local effective configuration; evaluate native Slurm configless distribution rather than introducing a new synchronizer. |
| `/opt/slurm/build` | Retain as operator build/archive material outside the user runtime publication. Do not copy build trees into the new shared runtime. |
| `/opt/sai_config` | Move site mapping assets to `runtime`; system security profiles remain locally installed files, with only their source templates shared. |
| `/opt/sbatch_examples` | Move to `examples`; update the existing provisioning writer, templates and managed example links together. |
| `/opt/envs` | Move the common login entry to `shell`. Associate software-specific environment scripts with their actual software version and existing modulefile. Preserve known script consumers until migrated. |
| Node-local `/opt/sai-cli` | Replace its package-owned runtime with the shared client and then remove the superseded package files through the package manager. |

The installed `sai` command must remain immediately available. Modulefiles can
offer explicit version selection, but users must not need `module load` on every
login merely to access the platform. A managed local PATH entry or compatibility
link is an integration file, not a second client installation.

## Conditions for a separately scoped infrastructure migration

1. Inventory the configured mounts, source owners and callers. Include native
   login files, node images, Slurm configuration, software modulefiles, Portal
   provisioning and user-facing templates. Separate reachable nodes, offline
   images and other sites; one login node is not a fleet inventory.
2. Publish reviewed platform contents without moving scientific binaries or
   rewriting user data. Build a versioned manifest and test an explicit candidate
   path with an ordinary user before switching shared entrypoints.
3. Canary the new platform mount and entrypoints on a login node and a compute
   node. Verify Python requirements, CLI authentication, login directory,
   module loading, representative jobs and failure/rollback paths.
4. Update the managed fleet and image definitions, then retire the four replaced
   shared mounts. Do not force-unmount a busy filesystem. A compatibility link
   needs a named current consumer and a removal condition; it must not conceal
   a second active implementation or permanent duplicate mount.
5. Remove obsolete wrappers only when the replacement implements their actual
   supported behavior. Resource commands, job reads, login selection and scheduler
   policy are different capabilities; an existing wrapper must not silently
   become an unsupported CLI command or broaden user scope.

Default-directory and submission-feedback improvements can be released through
the existing stable entrypoints before the physical mount migration. The
migration must not become a prerequisite for fixing those user-visible flows,
and their deployment must not be reported as completion of the mount migration.

## Standards

[FHS 3.0](https://refspecs.linuxfoundation.org/FHS_3.0/fhs/ch03s13.html)
describes package and provider directory trees under `/opt`; it does not require
an NFS mount per package. The
[Lmod installation guide](https://github.com/TACC/Lmod/blob/main/docs/source/030_installing.rst)
documents versioned software under a shared prefix and installation of common
code once for multiple hosts. The five-role layout above is the SAI site design,
not a claim that FHS mandates these exact category names.
