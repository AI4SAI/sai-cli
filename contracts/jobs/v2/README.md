# Organization job read scope

This schema extends the preceding exact-account DTO for an organization with
authorized project accounts. The root `subject` retains its own account/user
intersection; `subject.subaccounts` lists 1–63 sorted, unique exact account/user
intersections. An item must match one intersection. A null user applies only
to that account. These fields are issued by Portal, not inferred at the site.

The preceding schema remains valid for self, personal, project, exact Run reads
and organization scopes without child subjects. Old versions never acquire
subtree meaning. Consumers validate the version before accepting child rows.
