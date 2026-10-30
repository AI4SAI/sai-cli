# Project member computing permission

A user-controlled Agent discovers a readable project, identifies one existing
member, previews that member's current permission and asks the original Portal
service to enable computing. Native local queries remain independent. There is
no TUI administration page or alternate member/permission store.

## Authority and discovery

The optional Identity scope `sai.collaboration.members.read` permits the
currently authorized project/member directory and exact request/task reads.
Project names and codes are labels, not authority. Project IDs and membership IDs
come from the returned authorized pages. Project pages use an exclusive ID cursor;
member pages narrow to one project, support exact username filtering and use
an exclusive membership-ID cursor. Limit is1–100. No contacts, wallet records,
filesystem paths or raw task payloads are returned. These reads require no shell
access, storage scope or per-node native query.

The separate `sai.collaboration.compute.write` permits only the implemented
enable operation. Current project/organization management rules still apply:
project admins cannot promote their own authority or edit peer administrators.
The existing member must have current write/admin file access and the project
must have a computing account. Shared folders and read-only members are refused.
Existing device grants remain unchanged; registration does not constitute consent.

## One enabled permission, original execution

POST `/v1/account/cli/projects/{project_id}/members/{membership_id}/enable-compute`
accepts only `site_id`, the original role/compute/window `expected` tuple, and an
`Idempotency-Key`. It does not accept a replacement role, validity, quota, payment
account, invitation token, or immediate-effect flag. The tuple is obtained from
the exact current read and checked under the original domain locks. The domain
writer holds role/window fixed and changes only compute=false→true.

The global member relationship is delivered across the project's existing sites;
site_id selects context and does not turn it into a single-site grant. The adapter
checks the complete task group before commit using the existing compute-only
contract. If historical site cleanup would add a file/revocation task, the whole
request rolls back with `project_compute_requires_reconciliation`. The original
cleanup obligation is neither discarded nor performed by this action. Already
enabled members return a conflict without creating any task.

## Retry and readback

The existing middleware idempotency record stores the accepted task references
in the same transaction. A key reused with another body conflicts. A completed
request repeated after later permission changes returns its original acceptance;
it never re-enables the member. Replays still require current authorization.

CLI preview performs a read. `--apply --request-id ID` first looks up that user's
existing request; if found, it returns the original acceptance after binding its
project and member. Only the specific request-not-found result permits a fresh
member read and one POST. A network error never creates a new key or write retry.
Use `projects request ID` after uncertainty and `projects task TASK_ID` for each
returned task. The task response identifies requested and current task IDs and
generation, so later original-owner retry generations are not confused.

Accepted, task-completed, current member compute permission and current per-site
compute access are separate facts. An enabled association initially retains the
original submission hold until the original resource-limit handoff applies;
financial, Identity, QOS and site admission remain separately authoritative.
The client does not promise that arbitrary jobs may be submitted.

This slice enables existing project computation. New invitations, role/window
changes, disable/revoke, quota/budget edits and job cancellation retain their
separate services and future portable adapters. Source/schema tests are not
production or actual user-consent acceptance.
