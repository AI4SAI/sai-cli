"""Native account choices, independent of Portal membership and saved defaults."""
from argparse import Namespace
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import os
from typing import Any

from .native_account_tree import associations
from .native_values import invalid_native, local_options, native_text, native_user


@dataclass(frozen=True)
class LocalAccounts:
    values: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return self.values


def read_local_accounts(args: Namespace, *, environ: Mapping[str, str]) -> LocalAccounts:
    timeout = local_options(args, command="account local")
    user = native_user()
    if not user or native_text(user) != user or any(char in user for char in ",/|"):
        raise invalid_native()
    cluster, rows = associations(user=user, environ=environ, timeout=timeout)
    return LocalAccounts({"schema_version": "native.accounts/v1", "source": "sacctmgr",
        "authority": "native", "cluster": cluster, "actor": {"user": user, "uid": os.geteuid()},
        "observed_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "accounts": sorted({account for account, _, _ in rows})})
