# Terminal workbench design

This replaces the prior scope-first, tab-and-toolbar design. The full target is
in [the rebuild brief](docs/workbench-rebuild.md). The currently deployed terminal
is a migration baseline, not a visual or interaction requirement.

## One place for the work

The main surface is the user's work at the selected site. A compact context
line and one switch action are enough. Work names, their situation and recent
changes occupy the primary area. Funds, raw scheduler fields, source metadata,
filters and resource inventories do not fill the opening screen.

Use one browse-to-inspect-to-result flow. A wide terminal may retain the work
list beside the selected work; a narrow one gives the selected work or result
the full body. Return restores the relevant list or file position. Do not expose
backend object kinds as parallel top-level job/task menus.

## Context without repeated setup

The current site remains explicit. Server-resolved overview context may supply
a default account label and selector; subsequent reads still authorize. An
unavailable overview is not proof that the user has no readable work.

Default personal work discovery needs a bounded server operation across the
user's currently readable workspaces. The client must not fan out through every
project or call a single workspace 'all my work'. Account and site changes use
existing authorized names, never required raw-key text boxes. Do not silently
change site, payer, file mounts or execution authority when switching views.

## Work and result hierarchy

A work row leads with its name, human-readable state and the most relevant
observed change. IDs and full timestamps belong to detailed evidence. A state
is not a scientific progress percentage. Live queue and recorded history keep
their actual time and completeness, even when presented in one work surface.

A selected work item answers what happened and what the user can do next.
Running work emphasizes its state and available observations. Failure leads to
readable execution evidence. Finished work emphasizes actual results. Resource
allocation, location and costs are secondary details in the same context.

Do not present disabled or inapplicable actions as a permanent seven-button bar.
Discover less common actions in the existing command palette or contextual menu.
Plain viewing never opens a model window or silently submits a computation.

Results show the actual declared files. Activation opens a supported preview;
Save is adjacent to the selected file, including non-previewable binary files.
Only a user-chosen save destination or an intentional research request needs
free text in the everyday flow. Saving over SSH identifies the actual terminal
host; it must not claim the file was saved to the user's personal computer.

## Truth and failure

Never join Job and Run rows by the job number alone. The shared read contract
must provide sufficient execution evidence before a UI treats them as one.
Unlinked native work cannot acquire Run logs, outputs or settled charges.

Loading, empty, missing, denied and failed are distinct states. A failed read
must not show zero work or retain old data beneath a new object's heading.
Changing scope or object invalidates late responses. Return remains possible
while a request is pending. Manual snapshots retain their explicit refresh
behavior; live updates must not move keyboard focus or change the selection.

## Presentation

Use the established SAI palette, clear keyboard focus, compact spacing and
consistent controls. Highlight the user's current object and primary action.
Status uses words as well as color. Technical provenance is available without
competing with the task title, results or decision.

At 40 and 60 columns, preserve the primary evidence and action. At wider sizes,
use additional space for useful context rather than more permanent forms.
Keep one language throughout the interface. Filenames and scientific output
remain exact; money formatting is presentation only and never reprices facts.

## Verification

Drive the actual default entry and complete a meaningful work-to-result journey
without raw identifiers. Repeat with no history, many records, a delayed read,
a permission loss and a failed source. Verify back/refresh and file continuity.

Inspect actual rendered screens, not only widget bounds. Read-only transport,
permission checks, role packages and source cleanup remain required, but they
do not prove usability or scientific value. The user-visible journey and the
user's assessment must justify a product-complete claim.
