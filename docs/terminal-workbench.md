# Terminal workbench

Status: replacement source candidate, not deployed or user-accepted. This
replaces the former Overview-first, tabbed terminal. The full product and
remaining work are in [the rebuild brief](workbench-rebuild.md).

```bash
python3 -m pip install '.[tui]'
sai tui
sai tui --language en-US
```

Use the existing protected connection configuration. The site remains explicit;
the interface never changes compute site automatically. An interactive terminal
is required; JSON commands remain the scripting interface.

## Work to results

The opening screen shows your current native activity and recent recorded work.
Select a name with arrows and Enter. Completed work opens its files; failed work
opens its error log. Running work shows its state and available observations.
No account identifier, job number or partition text is required. When credentials
are missing, Sign in opens the existing device authorization flow inside the
terminal, with browser approval and cancel/retry.

Select a file to read its supported text preview. Save uses the existing
version-bound binary download and an explicit destination on the terminal host.
Existing files are never overwritten. Cancellation drains the transfer and
removes its private partial file. Reading or saving does not send a model prompt.
Escape returns to the same file page or work selection. Next/previous page
choices are visible in lists; content pages also have contextual navigation.

Start work opens Pilot's native browser entry with the chosen site and any
explicitly applied workspace. Pilot owns working directories, sessions,
computation preparation and Agent execution. Browser authorization remains
independent of the terminal's Identity token. This route is a paired delivery
dependency, not a second Portal computation page.

More and Ctrl+P expose actions appropriate to the current work: logs, results,
costs, statistics, allocation, registered location and detailed evidence.
Resource comparison, storage usage, account messages and named account choices
are secondary tools. There is no permanent seven-button mode bar or ID form.
Advanced numeric diagnostics remain available through `sai jobs show`.

## Existing authority, clearer interaction

Default recorded history uses `compute.my-runs/v1`: actor-bound, site-bound,
paginated and joined once to currently readable workspaces. The terminal never
fans out across projects. `sai runs recent` exposes this page as JSON.
An explicit `--workspace-key` instead narrows native and recorded reads to the
same account. A legacy native-account selector stays queue-only until a named
workspace is chosen. Storage and the login summary retain their own scopes.

Native activity and Run history remain separate observations. They are not
merged using a job number; native-only work cannot acquire managed files or
final charges. Trusted list-level execution association is still required for
the complete unified product. Source failure is visible, not an empty work list.

The existing file authority checks Run READ and the frozen directory separately.
Each preview rechecks the selected file page before content. Costs use the
existing billing owner, never a client price calculation. Native statistics
retain their observation limits. Location is an operator registration, not
proof of physical GPU identity or measured utilization.

One asynchronous reader serializes immutable request contexts and coalesces
refreshes. Navigation invalidates late responses. Home and ordinary state views
may update automatically; files, logs, costs, resources, allocation and location
remain manual observations. F5 replaces the current read. Pause/Resume appears
only where automatic updates exist. Refresh does not move keyboard focus.

Authentication loss clears protected content and offers login. Independent
file, cost or storage denial clears the corresponding evidence without erasing
still-authorized work. Returning rereads with current authority, then restores
position. Expired location registrations are removed by their earliest validity
deadline, without another network request or a polling timer.

## Migration and verification

The old `tui.py`, tab state and layout-only tests are removed. No alias or
subclass keeps the rejected interface alive. The shared presenters, safe result
saver and transport/permission contracts remain the authoritative implementations.

| Previous behavior | Replacement verification |
| --- | --- |
| Tab/filter/ID forms | Default CLI entry opens named work with no text fields |
| Separate queue and task pages | Work list retains honest source sections; no number-only join |
| File/log/cost detours | Real local HTTP journey restores file, cursor and context |
| Late responses and revocation | Delayed reads cannot restore old work; separate authority failures remain separate |
| Allocation/location expiry | Exact-deadline cases preserve the same allocation without another read |
| Binary save and cancellation | Existing range/grant protocol, no-overwrite publication and cancellation cleanup |
| Resource comparison and messages | Contextual choices preserve selection and independent account authority |
| Evidence formatting | Kept unit/unknown/path/decimal and language presenter checks |

The legacy resource preparation URL and Run console deep links remain explicit
secondary consumers until native Pilot accepts those exact references. Their
removal condition is a paired native replacement preserving resource/file
context and read authority. They are not the default Start work path or evidence
of an accepted end-to-end experience. Native job-to-console navigation is no
longer a workbench action; its existing protocol code is separate from this UI.

Local tests use bounded HTTP fixtures and actual Textual rendering at 40, 60 and
100 columns in Chinese/English. A local Portal/CLI pair verifies work discovery
and subsequent detail reads. These checks do not establish deployed producer
availability, physical-terminal behavior, real user comprehension or interest.
3D remains behind truthful task/allocation/asset/telemetry facts; see
[the digital-twin design](digital-twin-design.md).
