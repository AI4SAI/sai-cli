# Terminal workbench

Status: implemented read-only client; local interaction/HTTP validation only.

Install the optional extra and use the existing connection configuration:

```bash
python3 -m pip install '.[tui]'
sai tui
sai tui --site site-a --scope project-account --account project-example
```

An interactive terminal is required. Scripts should continue using the JSON
commands. Managed login-node connection settings retain their existing owner
and override restrictions. Installing the extra locally does not deploy a
shared login-node package or gateway.

## A useful first workflow

1. Open Resources and press Enter on one or two partitions. Compare CPU/GPU
   model, per-node CPU cores, total GPUs, nodes, QOS and published prices in
   the detail panel. Unknown facts remain unknown; no availability or price
   calculation is inferred.
2. Use View jobs to apply the most recently selected partition to the Jobs
   view. Change scope, account name/ID, partition or states and select Apply.
   The applied context remains visible; draft controls do not change authority.
3. Press Enter on a job for its separately authorized detail. Escape returns
   to the list. Native site-read mode is used when explicitly configured;
   otherwise the existing Portal transport is used. Neither path falls back.
4. Open Running estimates to request the independent billing DTO. Enter shows
   one item's amounts, price revision, source time and uncertainty. This is
   never a final charge. No match to a job is guessed from its numeric ID.

Storage rows in Resources are published products only, not quota usage or
file access. The separate Storage tab selects a stored quota sample or an
on-demand native Lustre quota query after an
explicit workspace key and Load; job account/scope never select that workspace.
`sai tui --storage-workspace-key org:example` preselects it. Editing the workspace
clears previous data immediately; Load and every refresh reauthorize the read.
`sai.storage.read` is required. State, effective versus target quotas, nullable
usage and observation time remain distinct; a negative remaining value means
the observed usage exceeds the effective quota. Native mode instead shows exact
byte/inode counters from authorized physical quota subjects. Native zero limits
mean unlimited; rows are not a whole organization pool total. It requires the
configured site gateway and never falls back to stored data. Changing source
clears old results immediately and discards late responses from the previous
source, using the same serialized reader.

There is no empty placeholder for unavailable task-result,
Pilot handoff, settled billing or hardware telemetry features.

## Interaction and data behavior

- F5 or Refresh requests an update. F6 pauses/resumes automatic refresh;
  Ctrl+Q exits. Tab and arrow keys use standard Textual focus/navigation.
- The active view refreshes every ten seconds; inactive views do not poll.
  Inspecting an estimate pauses that view's automatic refresh to preserve its
  exact snapshot. Escape or a manual refresh leaves that inspection.
- One background reader serializes client calls, including credential refresh.
  Repeated requests coalesce into the latest requested view/context. Changing
  scope clears old data and invalidates in-flight results. Network calls are
  still bounded by the existing HTTP timeout, not physically aborted.
- Authentication failure clears all cached display data and pauses polling.
  A permission or source error clears only the affected view; fee access does
  not imply job access or vice versa. Errors use the client-safe diagnostic.
  Failed views wait for manual refresh or re-entry rather than polling the
  same error indefinitely.
- Jobs retain the requested server limit and show truncation where the DTO
  supplies it. Estimates are a complete authorized server snapshot displayed
  in local pages of 100 rows. These pages do not claim server pagination or
  live atomicity across multiple requests.
- Backend text is rendered literally; Rich markup or terminal controls cannot
  become instructions to the display. Ordinary catalog prose may wrap.
- Narrow/short windows use compact controls; details scroll vertically and
  tables can scroll horizontally. Comparison remains a table of the same
  validated facts, not a new product or pricing model.

## Validation and remaining work

Headless tests exercise the real HTTP client through resource comparison,
partition selection, detail requests and independently denied estimates.
Delayed-result tests exercise scope replacement, old permission failures and
request coalescing. Nullable/duplicate estimate identities use snapshot-local
UI rows, not invented business identifiers. Small-window checks cover the
layout and accessible control positions; local synthetic screenshots are not
real infrastructure acceptance.

The full [unified workbench](unified-workbench.md) still needs authorized
task/results contracts, selected-object Pilot handoff, richer resource
eligibility and hardware telemetry. Native storage quota is implemented locally;
site installation, service-UID permissions and real Lustre behavior still require
acceptance. The privileged storage write adapter is not used by this UI or
packaged with the read gateway. Keep 3D after truthful data.
