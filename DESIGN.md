# Terminal companion design

People use SAI beside their existing SSH aliases, editor and native commands.
Agents invoke the same client from user devices and dedicated isolated VMs.
Keep local queries quick, business operations clear and machine results stable.
[Command scope](docs/terminal-scope.md) owns the operation boundary; this file
governs human presentation, not a restriction on Agent management coverage.

## One answer at a time

The existing login/status summary is a useful starting point: applied identity,
authorized funds or budget, relevant access problems and short notices.
It prints once and returns to the shell, without opening another application
or a full-screen work list. Its business facts come from Portal; local native
queries remain independent of that summary request.

Local job, GPU/CPU and quota queries should preserve the useful density and
defaults of the existing SSH helpers. Reuse the same observation for human and
JSON output. Avoid mandatory text entry, command catalogues or page navigation
before a common query. Agent calls use explicit inputs and never wait for TUI
interaction; they report the domain's required confirmation or operation state.

The native helper visuals are an existing product contract: job rows retain
their fixed columns and local timestamps; GPU rows retain the native Slurm IDX
positions with blue allocated and green idle cells, followed by a partition
table. Blocked nodes use red. CPU rows group by partition, with CPU/memory
allocation bars with adjacent counts and separate reported load/free memory; quota retains aligned native
usage, soft/hard limit and grace columns. `gpu` and `cpu` include node rows by
default. Use the existing Rich Table, Text, Columns and ProgressBar components,
not a custom ANSI/layout engine. GPU slots follow Slurm IDX order; unavailable
indices show `?`, never a made-up left-packed allocation. Rich wraps the slot
grid at cell boundaries. CPU ratios are allocated/effective total; below 80
columns the table prioritizes those allocations over OS reports. QOS appears
once per partition, without repeated totals or explanatory paragraphs. Color
follows the terminal and `NO_COLOR`. JSON does not import Rich.

Cost is an explicit inquiry. Show the account/site and whether the amount is a
running estimate or a settled charge. Use the existing command and server
contract. A selected native job may request a cost explicitly; keep job/account/
cluster/incarnation binding and separate business permission. Never estimate locally.

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
`sai tui` is a focused Textual query surface, distinct from one-shot `status`.
Available native queries use a single compact tab strip: jobs, GPU, CPU and quota;
account information is fetched only when selected. Arrows/Enter select an existing
job or partition, r refreshes, c reads an explicitly selected job estimate, and
q returns to the shell. One answer stays visible; no workspace tree, file manager,
Pilot orchestration or Portal page hierarchy belongs here. Native command names
and the existing dense resource tables remain familiar. The initial view uses
an installed native tool when present; a failed local read never changes source.

Refresh only the visible query, with a visible cadence and `p` to pause/resume.
Keep the selected row, scroll position and focus instead of clearing a list while
reading. Suspend polling during a selector or job detail. CPU/GPU node details
reuse the same refreshed observation. An account chooser displays actual names
as soon as its authorized directory loads; it needs no adjacent load button.

Job, partition and quota selections persist across view changes. Native job
account choices come from the current user's Slurm associations when the selector
opens; the first queue does not wait for this discovery. Quota chooses real
directories through Textual's directory tree without typing or deriving paths
from account names. Business account selection retains its Portal owner.

Job inspection gives the map the content area and keyboard focus. Arrow and
page keys scroll; Escape restores the original list position. Refresh rereads
the selected detail, preserving its position; rejection clears the old detail.
The default detail uses a compact CPU/NUMA tree and the selected GPUs' connection
matrix. Where placement is known, the tree includes only NUMA domains with this
job's mapped CPUs or GPUs, and only its selected GPUs. CPU and GPU assignments
may span different domains; keep both. The title identifies this job projection,
and unknown CPU locality stays explicit. `i` expands all domains, PCIe ancestry
and the complete GPU matrix from the same
observation, without another read. Exact Slurm CPU ranges remain concise;
per-thread panels are removed. Native Slurm sockets may be configured NUMA
groups and are not labeled as physical CPU packages. Resource tables and node
details label these dimensions as Slurm configuration too. Draw PCIe and fabric edges
only when the recorded native observation supplies them. Keep missing, expired
and replaced observations distinct from an idle device.

When a recorded Slurm-to-Linux CPU mapping is available, mark the job's logical
CPU count on the corresponding NUMA rows. Show exact Linux IDs only on expansion.
Absent mapping means unknown locality; GPU affinity never substitutes for it.


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
