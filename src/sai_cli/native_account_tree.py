"""Resolve a local Slurm account subtree through its native association reader."""
from __future__ import annotations

from typing import Mapping

from .errors import ConfigError, UnavailableError
from .native_process import read_native_json, read_native_output
from .native_values import invalid_native, native_environment, native_header, native_text


def associations(*, environ: Mapping[str, str], timeout: float,
                 root: str | None = None, user: str | None = None) -> tuple[str, list[tuple[str, str, tuple[str, ...]]]]:
    environ = {key: value for key, value in native_environment(environ, filter_prefix="SQUEUE_").items()
               if not key.startswith(("SACCTMGR_", "SCONTROL_"))}
    context = read_native_json(["scontrol", "--json", "ping"], environ=environ, timeout=timeout)
    cluster, _ = native_header(context)
    raw = read_native_output(
        ["sacctmgr", "-nP", "show", "assoc", *(["WithSubAccounts"] if root is not None else []), "where",
         "cluster=" + cluster, "account=" + root if root is not None else "user=" + user,
         "format=Cluster,Account,User,Lineage"],
        environ=environ, timeout=timeout, max_output_bytes=1024 * 1024, reject_stderr=True,
    )
    try:
        rows = raw.decode("utf-8").splitlines()
    except UnicodeError as exc:
        raise invalid_native() from exc
    paths: dict[str, tuple[str, ...]] = {}
    result = []
    for row in rows:
        fields = row.split("|")
        if len(fields) != 4:
            raise invalid_native()
        row_cluster, account, row_user, lineage = fields
        if (row_cluster != cluster or not account or any(char in account for char in ",/|")
                or native_text(row) != row or not lineage.startswith("/") or not lineage.endswith("/")):
            raise invalid_native()
        path = lineage[1:-1].split("/")
        if user is not None and row_user != user:
            raise invalid_native()
        if row_user:
            if path[-1] != "0-" + row_user:
                raise invalid_native()
            path.pop()
        if not path or path[-1] != account or (root is not None and root not in path) or not all(path):
            raise invalid_native()
        if account in paths and paths[account] != tuple(path):
            raise invalid_native()
        paths[account] = tuple(path)
        result.append((account, row_user, tuple(path)))
    return cluster, result


def account_tree(root: str, *, environ: Mapping[str, str], timeout: float) -> tuple[str, list[str]]:
    if not root or any(char in root for char in ",/|"):
        raise ConfigError("--with-subaccounts requires one literal -A account")
    cluster, rows = associations(root=root, environ=environ, timeout=timeout)
    paths = {account for account, _, _ in rows}
    if not paths:
        raise UnavailableError("the native account hierarchy is unavailable",
                               code="native_account_tree_unavailable")
    # Ordinary users may see their child associations without the parent row.
    return cluster, sorted({root, *paths})
