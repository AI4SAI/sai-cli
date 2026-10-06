# Product

## Register

product

## Purpose

SAI helps researchers use shared computing resources. Terminal users already
work in a shell with Slurm, Linux tools, scripts and editors. The SAI client
adds authorized information those tools do not have, without making users move
their work into another application.

The full terminal workbench is rejected. A unified backend means consistent
facts and permissions, not the same features or screens in every client. The
[terminal scope decision](docs/terminal-scope.md) replaces the full-workbench
brief. Source now replaces the full-screen shell with the existing compact
account summary. Installed-runtime and human-usability acceptance remain
separate from this source change.

## Terminal value

The useful questions are specific to SAI:

- Which account and project am I using here, and is its site access effective?
- What funds or project budget may I use, and what is already committed?
- What does this computation cost, using SAI's prices and billing authority?
- Is an access issue, expiring entitlement or relevant notice affecting my work,
  and where can I resolve it?

Start with the existing `sai status` summary and explicit cost commands. A
short answer that returns to the shell is often the whole interaction. Do not
turn these questions into an account-management application. An interactive
selector is justified only where choosing an authorized name removes repeated
lookup or technical input. No full-screen home is required by this product.

Queue inspection, submission, logs, files and native statistics remain part of
the user's normal tools. Existing API commands can serve remote reads, scripts
and Agent integrations without acquiring a corresponding TUI page.

## Responsibilities

Pilot owns its native Web computation experience, Agent, sessions and job
plugin. Portal owns membership, site access, business policy and final billing.
Identity owns authentication. Site systems supply dynamic native facts through
authorized site readers. The user chooses the compute site.

The CLI stays read-only and consumes those owners' contracts. It does not add
native-command fallbacks, a scheduler, account policy or a pricing engine.
Reducing the TUI does not remove shared APIs needed by WebUI, Pilot or Agent.
Those consumers do not depend on a terminal workbench being available.

## Interaction and appearance

Give the answer first: a named context, a relevant value or problem, and a useful
next action. Preserve the shell, scrollback and current work. Known context and
authorized choices replace requests to type platform IDs. Viewing another
account does not change the shell's submission account, directory or payer.

Use terminal-native surfaces, restrained SAI color, clear spacing and readable
amounts. Normal information stays quiet; color accompanies words. Full-width
frames, permanent toolbars, technical provenance and unrelated modules must not
compete with the answer. See [the terminal design](DESIGN.md).

Codex CLI, Claude Code and OpenCode inform focused interaction and progressive
disclosure. Their complete Agent interfaces are not a template for this client.

## Acceptance

For each interaction, identify the missing native capability and compare it
with the existing one-shot CLI. The user should obtain a useful SAI answer and
return to work without learning a navigation system or copying internal IDs.
If interaction adds no value, keep the command and omit the screen.

Check Chinese/English, narrow/wide terminals, permission loss and unavailable
sources. Unknown funds are not zero; funds alone cannot prove submission is
allowed. Tests and deployment establish technical behavior, not user interest.

## Digital twin

WebUI's role-filtered hardware view and Agent-readable facts remain in scope.
Real task allocations, registered assets and measured telemetry are separate
facts. Parameterized 3D comes from an asset inventory after data is trustworthy.
It does not require a terminal hardware tree. See [the design](docs/digital-twin-design.md).
