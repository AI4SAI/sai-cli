# Terminal companion design

The user is already working in an SSH shell, often beside an editor or a native
command. SAI should answer a small platform-specific question and let that work
continue. [Terminal scope](docs/terminal-scope.md) owns feature selection; this
file governs the presentation of the retained interactions.

## One answer at a time

The existing login/status summary is the starting point: applied identity,
authorized funds or budget, relevant access problems and short notices.
It prints once and returns to the shell. It does not open a full-screen work
list or require a round trip through Portal or Pilot.

Cost is an explicit inquiry. Show the account/site and whether the amount is a
running estimate or a settled charge. Use the existing command and server
contract; do not build a queue browser merely to give access to cost.

Preserve useful existing login information and native-command guidance. Do not
replace it with a menu the user must enter to recover the same information.

## Interaction only where it saves work

Use a small named chooser when a necessary SAI selection would otherwise require
finding and pasting an account or project identifier. Selection should answer
the question in progress, not open another product section. Do not add a chooser
until an authorized directory supports that exact purpose.

One choice needs arrows, Enter and Escape, with visible instructions. Escape
returns without changing the shell or submission context. Optional search can
help a long list; empty technical forms cannot be the default experience.
No sidebar, task tree, resource browser, file manager or command catalogue is
part of the terminal companion.

## Information hierarchy

Lead with the human account/project name and relevant site. Show a genuine
blocker before routine values. Keep cash, Credit, budget and running estimates
distinct, and do not imply organization funds belong exclusively to one member.
Technical references, timestamps and detailed provenance are secondary, while
stale or incomplete evidence must be clear where it affects a decision.

Use aligned text, modest spacing and the existing SAI accent sparingly. Respect
the terminal background and monochrome output. Status requires words as well
as color. Avoid persistent frames, repeated headings, decorative counters and
empty sections. At 40 columns, preserve the answer and action through wrapping;
extra width should improve reading, not reveal additional product modules.

Financial display rounds for readability without changing JSON precision or
turning a nonzero amount into zero. Labels use one selected language; names,
filenames and scientific content remain exact.

## Truth and verification

Current login context, selected read scope, file access and submission payer
remain independent. A summary does not silently change any of them. Only the
server may report admission or a reason for restriction; the client must not
infer it from a balance, scheduler account name or an unread message.

Distinguish missing permission, failed reads, unknown values and real zero.
Do not retain old account facts beneath a newly selected account's name. Any
retained interaction reuses existing authentication, authorization and bounded
read behavior rather than adding a cache or parallel state machine.

Review rendered output in narrow/wide and monochrome terminals. Verify that a
person can identify the context, the useful answer and any needed action, then
continue using the shell. A successful tour of many screens is not acceptance.
