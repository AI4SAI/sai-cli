"""Cancelable focused queries invoke the same CLI commands and JSON contracts."""
from __future__ import annotations

import asyncio
from argparse import Namespace
from collections.abc import Mapping
from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import signal
import sys
from typing import Any

from .errors import AuthenticationError, ConfigError, ContractError, ForbiddenError, SaiCliError, UnavailableError


@dataclass(frozen=True)
class Read:
    view: str
    selection: str = ""
    job: Any = None

    @property
    def remote(self) -> bool:
        return self.view in {"account", "accounts", "cost"}


class Queries:
    def __init__(self, args: Namespace, environ: Mapping[str, str]):
        self.args, self.environ = args, dict(environ)
        self.directory, self.home = os.getcwd(), str(Path.home())
        self.account = environ.get("_SAI_LOGIN_ACCOUNT") or None
        self.views = tuple(view for view, binary in (
            ("jobs", "squeue"), ("gpu", "sinfo"), ("cpu", "sinfo"), ("quota", "lfs"),
        ) if shutil.which(binary, path=environ.get("PATH", os.defpath))) + ("account",)

    async def _command(self, arguments: list[str], *, remote: bool = False) -> dict:
        from .cancellation import refresh_cancel_grace
        cancellation_grace = refresh_cancel_grace(self.settings().timeout_seconds) if remote else 1
        if remote:
            # These are the same documented connection inputs as the batch CLI.
            for name in ("config", "profile", "base_url", "site", "cache", "timeout", "no_cache", "allow_insecure_http"):
                value = getattr(self.args, name, None)
                if value not in (None, False):
                    arguments += ["--" + name.replace("_", "-")] + ([] if value is True else [str(value)])
        elif self.args.timeout is not None:
            arguments += ["--timeout", str(self.args.timeout)]
        source = str(Path(__file__).resolve().parent.parent)
        # Separate process group lets cancellation terminate only this read and
        # its native children. No Shell, interactive login or alternate authority.
        entry = "import sys;sys.path.insert(0,sys.argv.pop(1));from sai_cli.cli import entrypoint;entrypoint()"
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-I", "-P", "-B", "-c", entry, source, *arguments,
            stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE, env=self.environ, start_new_session=True,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), cancellation_grace if remote else 2 * (self.args.timeout or 30) + 5,
            )
        except TimeoutError as exc:
            raise UnavailableError("The read timed out; refresh to retry.") from exc
        finally:
            if process.returncode is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    await asyncio.wait_for(process.communicate(), cancellation_grace)
                except TimeoutError:
                    os.killpg(process.pid, signal.SIGKILL)
                    await process.communicate()
        if process.returncode != 0:
            try:
                error = json.loads(stderr)["error"]
                code, message = error["code"], error["message"]
                if not all(isinstance(value, str) and len(value) <= 4096 and value.isprintable() for value in (code, message)):
                    raise ValueError("invalid diagnostic")
            except (ValueError, KeyError, TypeError):
                raise UnavailableError("The query failed; retry with the corresponding CLI command.") from None
            if process.returncode == 3:
                raise AuthenticationError(message, code=code)
            if process.returncode == 4:
                raise ForbiddenError(message, code=code)
            raise SaiCliError(code=code, message=message, exit_code=process.returncode)
        try:
            return json.loads(stdout)
        except ValueError as exc:
            raise ContractError("The query did not return a valid result.") from exc

    def settings(self):
        from .config import resolve_settings
        return resolve_settings(self.args, self.environ)

    async def read(self, request: Read):
        if request.view == "job_accounts":
            from .local_accounts import LocalAccounts
            return LocalAccounts(await self._command(["account", "local"]))
        if request.view == "jobs":
            from .local_jobs import LocalJobs
            from .contracts import JobItem
            command = ["jobs", "local", "--limit", "500"]
            if request.selection == "identity" and self.account:
                command += ["-A", self.account, "--with-subaccounts"]
            elif request.selection.startswith("account:"):
                command += ["-A", request.selection.removeprefix("account:"), "--with-subaccounts"]
            data = await self._command(command)
            return LocalJobs(cluster=data["cluster"], actor=data["actor"]["user"], uid=data["actor"]["uid"],
                filters=data["filters"], observed_at=data["observed_at"], has_more=data["has_more"], warning_count=data["warning_count"],
                items=tuple(JobItem.from_payload(row, request_id="native-squeue", text_limits={key: 16384 for key in row}) for row in data["items"]))
        if request.view in {"gpu", "cpu"}:
            from .local_resources import LocalResources
            return LocalResources(await self._command(["resources", "local", "--kind", request.view]))
        if request.view == "allocation":
            from .native_topology import NativeTopology
            item = request.job["item"]
            value = await self._command(["jobs", "local", "--job-id", item.canonical_id, "--with-interconnect"])
            if value["cluster"] != request.job["cluster"] or any(value["job"][key] != item.values[key]
                for key in ("job_id", "array_task_id", "slurm_user", "slurm_account", "submit_time")):
                raise ContractError("The job changed; return to the list and refresh before inspecting it.")
            return NativeTopology(value)
        if request.view == "quota":
            from .local_quota import LocalQuota
            path = self.home if request.selection == "home" else request.selection or self.directory
            return LocalQuota(await self._command(["storage", "local-quota", path]))
        settings = self.settings()
        if request.view == "account":
            from .overview import AccountOverview
            account = request.selection or self.args.account or self.account
            command = ["status", "--format", "json"] + (["--account", account] if account else [])
            return AccountOverview.from_payload(await self._command(command, remote=True), site_id=settings.site_id,
                                                account=account, request_id="account-overview")
        if request.view == "accounts":
            from .default_account import DefaultAccountState
            return DefaultAccountState.from_payload(await self._command(["account", "defaults"], remote=True),
                                                     site_id=settings.site_id, request_id="account-directory")
        if request.view == "cost":
            from .contracts import JobCostResult
            if settings.cluster_id is not None and settings.cluster_id != request.job["cluster"]:
                raise ConfigError("The configured remote cluster differs from this local job.")
            job = request.job["item"]
            command = ["jobs", "cost", job.canonical_id]
            if not settings.managed_login_node:
                command += ["--cluster", request.job["cluster"]]
            if request.selection == "identity" or request.selection.startswith("account:"):
                choices = (await self.read(Read("accounts"))).values["choices"]
                selected = self.account if request.selection == "identity" else request.selection.removeprefix("account:")
                account = next((row for row in choices if row["name"] == selected), None)
                if account is None:
                    raise ForbiddenError("This native account is not in the authorized SAI account directory.")
                command += ["--scope", account["kind"] + "-account", "--account-id", account["id"]]
            result = JobCostResult.from_payload(await self._command(command, remote=True), request_id="job-cost")
            returned = result.observation.items[0].values
            if any(returned[key] != job.values[key] for key in ("job_id", "array_task_id", "slurm_account", "slurm_user", "submit_time")):
                raise ContractError("The job changed; return to the list and refresh before reading its estimate.")
            return result
        raise ConfigError("Unknown terminal query")
