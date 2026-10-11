# First useful task

The client works for people and independently chosen Agents. A cluster login
already provides the native environment; a personal device uses normal Identity
authorization and Portal APIs. A dedicated user VM follows the same device path.
Pilot is not required.

## Already on a cluster

Use the existing `sqm`, `sqa`, `gpu`, `cpu` and `quota` aliases. These local reads
need no browser login. `sai tui` offers focused selection and refresh; `q` returns
to the shell. For scripts and Agents, discover the corresponding batch commands:

```bash
sai describe jobs local
sai jobs local
```

The result is the current Unix user's native view. Use `sai` when you need the
SAI account summary; its business facts require your normal SAI login separately.

## Install on your device

Python 3.11 or newer is required; independent-client validation currently covers
Linux. Windows and macOS are not yet qualified. The repository remains private without an approved public
release: obtain the reviewed wheel and trusted service URL from your
SAI service operator. Do not assume a package with a similar public name is this
client. Check the supplied artifact checksum before installation.

In a directory you control, with the provided wheel present:

```bash
python3 -m venv .sai-env
. .sai-env/bin/activate
python -m pip install ./sai_cli-0.1.0-py3-none-any.whl
sai --version
sai describe --format table
```

Use the filename supplied for your version. The batch client needs no third-party
runtime packages, Slurm, Lustre mounts, shared cluster installation or hosted VM.
The optional TUI has separate dependencies; see [terminal scope](terminal-scope.md).

## Sign in and choose a site

Use the service URL supplied by your operator. The command verifies its public
connection settings and Identity discovery, then saves a new user configuration.
It never overwrites existing profiles or credentials. A site is not required.

```bash
sai configure https://portal.example.org --format table
sai auth login
sai sites --format table
```

Use your actual trusted URL in place of the example. `configure` requires the
paired server's public CLI configuration endpoint. An older server reports a
configuration error; it does not guess an Identity address. Existing reviewed
profiles continue to work; see the [configuration reference](../README.md#configure).
To connect a second independent service, use `--config PATH` and keep that option
on subsequent commands. A repeated configure verifies the same connection while
preserving custom settings. The shared cluster installation is already configured.

Open the URL printed by login in your browser and confirm the device code. Keep
the terminal command running until confirmation completes. The CLI stores a
protected renewable device credential; passwords and tokens are never copied
into commands. If a valid session already exists, reuse it. For an Agent that
cannot keep the login command running, use `--no-wait` and later `--resume`.

Choose your site from the returned names. For example, after selecting the
returned `site-a` ID:

```bash
sai resources catalog --site site-a --format table
sai account defaults --site site-a --format table
```

The first command shows published specifications and prices. The second shows
your computing account choices and existing site application receipts. Neither
changes your default. A published site may still require access authorization;
listing it does not grant access or prove spare capacity.

The paired site directory and shared client are deployed; the
[delivery map](product-delivery.md#shared-first-use-delivery) records the validation scope.
An older deployment may not provide discovery. Report that mismatch instead of treating
an error as an empty directory or guessing IDs. Site choice remains explicit.

## Give your Agent the matching skill

```bash
sai skill --format markdown
```

This prints the complete `SKILL.md` shipped with your installed CLI, without
network access or login. Save it as `sai-cli/SKILL.md` in your Agent host's
supported skill location, or supply its contents through that host's instruction
mechanism. Check before replacing an existing customized skill. The command
does not install into or reconfigure an Agent host. Refresh the copy when you
upgrade the CLI.

For automation, `sai skill` returns `cli.skill/v1` JSON with `client_version`,
`name` and `content`. `sai describe` remains the operation/argument authority.
These offline commands run even without a configured service.

Try a useful read: "Show the published resources and my available computing
accounts at the site I selected." The Agent should discover names and IDs,
explain the answer, and preserve your selection. Then an explicitly requested
management task can use [the existing default-account workflow](portal-management.md).
It needs separate write authorization and reports central acceptance separately
from site application. When permission is missing, authorize that operation:

```bash
sai auth login --for account set-default
```

Confirm in your browser, then continue the requested task. The command includes
the permission needed to read its result, keeps current granted permissions and
does not perform the account change. It updates your protected device login;
the connection profile stays unchanged. For an Agent, add `--no-wait` and later
use `sai auth login --resume` without repeating the target. A command group such
as `--for invitations` requests the group's published permissions. Server-side
roles and site access still apply. The shared client and invitation optional scopes are deployed. A user must still
approve any newly requested permission; publication does not expand an existing
login or perform the task.

## Recover or upgrade

A missing session calls for `sai auth login`; a permission denial requires the
relevant account/site authorization, not a broader native query. An unavailable
service is different from having no resources. Keep the bounded error code and
request ID for support, without exporting credentials or raw logs.
If the local connection is missing, repeat `sai configure` with your trusted
service URL. If a file already points elsewhere, retain it and use a separate
`--config PATH`; do not copy credentials or remove an existing login to repair it.
If configuration reports a connection environment conflict, unset only the
listed old `SAI_*` variables and retry. Matching overrides are accepted; a saved
profile must not silently lose to an old service address in the Shell.

Install a reviewed newer wheel with the same environment's `python -m pip install`
and `--upgrade`. Keep the earlier wheel for `--force-reinstall` rollback. Updating
the program does not alter your saved profile or grant new scopes. Afterward,
check `sai --version`, export the matching skill and repeat the same first read.
Record which artifact was exercised; one successful Linux installation does not
establish every platform or a live deployment's compatibility.
