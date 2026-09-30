# Bounded SSH terminal acceptance

Recorded 2026-10-01. This is a real SSH/PTY check of the workbench on one login
host, using an ordinary account and synthetic loopback HTTP facts. It does not
establish production identity/API access or a shared CLI release switch.

## Runtime and method

The existing formal builder produced a clean, mainline-reachable `--with-tui`
archive from commit `1933a436e929e50c9c8a28e74e80710e39686b14`.
Runtime archive SHA-256:
`63f300533bd54e96e40e51cdeeb121ad08e1cb391ddf9297ff11f7a3b0505d69`.
The remote archive matched, and the observed TUI/client/placement module hashes
matched its contents. Python was 3.12.3 and Textual 8.2.8.

A temporary fixture launcher loaded that runtime and called real `Workbench.run()`.
It did not change the managed wrapper or its configuration. All user interactions
used real terminal bytes: command palette, arrow/End/Enter, SGR mouse input and
window-change signals. Read-only instrumentation observed the current widgets,
rendered terminal text, HTTP calls and process resources. It did not set app
selection or invoke app actions. The fixture read no user credential cache and
served no live scheduler, billing, storage or asset information.

The operator used one persistent SSH connection at a time. Terminal output and
the forwarded test-control HTTP channel were drained concurrently, so the
driver could not block itself by filling the terminal pipe. The output capture
was bounded, and login banners were excluded. Source archives, fixture hashes,
requests, terminal modes and cleanup receipts were checked independently.

## Passed observations

| Run | Observed result |
| --- | --- |
| English smoke | 20.002 seconds, task-to-location read, normal exit and terminal restoration |
| Recovery check | 70.021 seconds, seven scenarios, including project reselection after Run denial |
| Chinese continuous | 840.021 seconds, 12 scenarios at 100×32, 60×24 and 40×18 |
| English supplementary | 70.021 seconds, seven scenarios with `screen-256color` and actual `NO_COLOR` |

The continuous run covered manual location/statistics reads, 200ms source delay,
registration expiry, independently disabled location reads, source 503, Run 403,
project recovery and final authentication 401. It made 30 product HTTP requests,
with at most one active read. Manual evidence views made no extra requests while
idle. Expiry removed registrations and kept the same allocation; Run denial
cleared protected task data; authentication failure paused refresh.

The supplementary run used a separate two-second delayed response. All three
100→40→60-column window signals occurred while that response was still pending;
the final 60×24 view settled after exactly one response. It then disconnected
SSH and reconnected to confirm that the fixture process and listener had ended
after SIGHUP. This proves cleanup, not restoration of an interrupted CLI session.

Normal Ctrl+Q exits restored local and remote terminal modes, emitted matching
alternate-screen enter/leave sequences and restored the visible cursor. On SSH
disconnect, remote terminal-mode readback was unavailable and is not claimed.

## Resource observations and limits

The instrumented 14-minute process increased from 52,872 to 74,536 KiB RSS.
After the first 120 seconds it ranged from 57,864 to 74,536 KiB; in the final
120 seconds it increased by 1,196 KiB. That final window held six threads and
nine file descriptors. Mean CPU over the post-warmup window was approximately
2.5% of one core, including the HTTP fixture and screen observer.

These values do not prove an unbounded leak-free process. Longer runs and
profiling without the observation overhead remain necessary. Physical terminal
fonts, GUI-emulator diversity, clipboard/OSC52, unstable networks, two-hour use,
production authentication and real backend data were not verified here.

Early attempts exposed test-driver issues: a startup handshake race, an invalid
synthetic title, a menu-selection assumption, forwarded-HTTP backpressure and an
insufficient resize observation window. Those failed receipts remain separate;
they were not converted into passes. The final runs used corrected drivers and
the same product runtime. No product behavior was loosened for acceptance.

All test processes/listeners stopped. Evidence was copied back and checked
before the exact temporary remote tree was removed. Production command paths,
shared publication, configuration, workloads and user data were unchanged.
