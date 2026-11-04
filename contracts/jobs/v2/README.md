# Organization job read scope

This schema extends the preceding exact-account DTO for an organization with
authorized project accounts. The root `subject` retains its own account/user
intersection; `subject.subaccounts` lists 1–63 sorted, unique exact account/user
intersections. An item must match one intersection. A null user applies only
to that account. These fields are issued by Portal, not inferred at the site.

The preceding schema remains valid for self, personal, project, exact Run reads
and organization scopes without child subjects. Old versions never acquire
subtree meaning. Consumers validate the version before accepting child rows.

Rows may include the optional `pending_reason` code/account from the same native
pending observation, with the original `AssocGrpJobsLimit` reason preserved.
The blocking account can be an ancestor; it never broadens the signed subject.
See [native jobs](../../native-jobs/v1/README.md) for native description and display semantics.
