# Managed output text reads

`compute.run-artifact-content/v1` reads one current UTF-8 section, at most 65536
bytes, from an explicitly selected Run output. Browser and CLI use the existing
`/v1/account/compute/runs` and `/v1/compute/cli/runs` prefixes, followed by
`/{run_ref}/artifacts/{artifact_ref}/content`. Queries contain workspace/site,
optional `artifact_cursor` (the selected 100-item list page), and optional
`cursor` from the previous content response. Client-supplied paths are rejected.

Every call checks current Run READ and independent applied file READ, resolves
one current output page, then uses the existing site reader as the Run owner.
An original Pilot Session or active model window is not needed. No submission,
price calculation, new file service or archive is created.

`available` includes UTF-8 text, exact byte offsets, metadata, a file version and
completion. Empty available content at offset zero is an empty file. `missing`,
`unsupported` and `changed` contain no content and no continuation. Source or
permission failure is an HTTP error, never empty success. Terminal controls
remain exact in JSON and are escaped for visual rendering. HTML is plain text.

The opaque version derives from native device/inode/size/mtime/ctime and is
checked before and after reading. A continuation binds that version and offset;
changed files require an explicit fresh read, never concatenation across versions.
This is a current file observation, not immutable content or proof of a scientific
result. Symlinks, nonregular targets and cross-filesystem files are rejected by
the existing safe descriptor-based reader. Binary or non-UTF-8 data is not previewed.

This bounded reader does not implement a bulk file download. Packaging, site and
center installation, shared-client publication and real-user acceptance remain
separate from paired source and local file/HTTP/browser tests.
