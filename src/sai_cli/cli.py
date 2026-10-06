"""Command-line parser and stable process behavior."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from typing import Mapping, Sequence, TextIO
from urllib.parse import urljoin, urlsplit, urlunsplit

from . import __version__
from .auth import (
    DeviceAuthorization,
    OidcClient,
    TokenProvider,
)
from .capability import CapabilityProvider
from .client import JobQuery, PortalClient, clean_states
from .config import Settings, resolve_settings
from .contracts import ACCOUNT_VERIFICATION_PATH
from .errors import AuthenticationError, ConfigError, ContractError, SaiCliError
from .oidc import OidcPending, OidcSlowDown
from .overview_view import render_overview
from .render import (
    render_account_status, render_json, render_resource_catalog,
    render_running_estimate_table, render_site_allocation, render_site_jobs,
    render_storage_quota_summary, render_native_quota,
    render_table,
)
from .site_jobs import SiteJobAllocationResult, SiteJobResult
from .site_placement import SiteJobPlacementResult
from .render import render_site_placement
from .storage_summary import clean_workspace_key, render_storage_workspaces
from .transport import JsonTransport


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sai",
        description="Read-only command-line client for SAI compute services",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    _add_connection_arguments(parser)

    commands = parser.add_subparsers(dest="command", required=True)
    for name, description in (
        ("status", "show SAI account, funds and access information"),
        ("tui", "show a compact SAI summary and return to the shell"),
    ):
        overview = commands.add_parser(name, help=description, description=description)
        _add_connection_arguments(overview, suppress_defaults=True)
        overview.add_argument("--account", help="authorized account to view (does not change your submission account)")
        overview.add_argument("--language", choices=("zh-CN", "en-US"), default="zh-CN", help="summary language (default: zh-CN)")
        if name == "status":
            overview.add_argument("--format", choices=("json", "table", "tui"), default="json")
        else:
            overview.set_defaults(command="status", format="tui")
    runs = commands.add_parser("runs", help="read your managed computations and declared outputs")
    run_commands = runs.add_subparsers(dest="runs_command", required=True)
    for command, description in (
        ("workspaces", "list account scopes where you may read your managed computations"),
        ("recent", "read your recorded computations across readable accounts at this site"),
        ("list", "list your managed computations, including completed runs"),
        ("show", "show the recorded state of one managed computation"),
        ("cost", "read the independently authorized final cost of one managed computation"),
        ("stats", "read one bounded native step observation of a managed computation"),
        ("placement", "read registered node locations bound to one current managed computation"),
        ("logs", "read a bounded page of a managed run's stdout or stderr"),
        ("files", "list current files in a managed run's declared outputs"),
        ("read", "read a bounded text section from one authorized output file"),
        ("download", "save one complete authorized output file without overwriting"),
    ):
        run_parser = run_commands.add_parser(command, help=description)
        _add_connection_arguments(run_parser, suppress_defaults=True)
        if command != "recent":
            run_parser.add_argument("--workspace-key", required=command != "workspaces", help="authorized read scope: personal:<id>, org:<id>, or project:<id>")
        if command not in {"list", "workspaces", "recent"}:
            run_parser.add_argument("run_ref", help="managed run reference returned by runs list")
        if command in {"workspaces", "list", "recent", "files"}:
            run_parser.add_argument("--limit", type=int, default=100 if command == "files" else 50,
                                    help="maximum rows in one page (1-100)")
        if command in {"workspaces", "list", "recent", "logs", "files", "read"}:
            run_parser.add_argument("--cursor", help="next cursor returned by the previous page")
        if command in {"read", "download"}:
            run_parser.add_argument("--artifact-ref", required=True, help="file reference returned by runs files")
            run_parser.add_argument("--artifact-cursor", help="request cursor of the selected file list page")
        if command == "download":
            run_parser.add_argument("--output", required=True, help="new local file path; existing files are never replaced")
        if command == "logs":
            run_parser.add_argument("--stream", choices=("stdout", "stderr"), default="stdout")
            run_parser.add_argument("--max-bytes", type=int, default=65536, help="maximum log bytes (1-65536)")
        _add_format_argument(run_parser)
    jobs = commands.add_parser("jobs", help="read authorized scheduler jobs")
    job_commands = jobs.add_subparsers(dest="jobs_command", required=True)

    list_parser = job_commands.add_parser("list", help="list jobs in an authorized scope")
    _add_connection_arguments(list_parser, suppress_defaults=True)
    _add_job_scope_arguments(list_parser)
    list_parser.add_argument("--partition", help="partition narrowing filter")
    list_parser.add_argument("--limit", type=int, default=100, help="maximum jobs (1-500)")
    _add_format_argument(list_parser)

    for command, description in (
        ("show", "show one authorized job"),
        ("allocation", "show a job's allocation snapshot from the site gateway"),
        ("placement", "show operator-recorded locations for a job's allocated nodes"),
    ):
        detail_parser = job_commands.add_parser(command, help=description)
        _add_connection_arguments(detail_parser, suppress_defaults=True)
        detail_parser.add_argument("job_id", help="job identifier, including an array task suffix")
        _add_job_scope_arguments(detail_parser)
        _add_format_argument(detail_parser)

    cost_parser = job_commands.add_parser("cost", help="show non-final running job cost estimates")
    _add_connection_arguments(cost_parser, suppress_defaults=True)
    _add_job_scope_arguments(cost_parser)
    cost_parser.add_argument("--partition", help="partition narrowing filter")
    _add_format_argument(cost_parser)

    resources = commands.add_parser("resources", help="read published site resource specifications")
    resource_commands = resources.add_subparsers(dest="resources_command", required=True)
    catalog_parser = resource_commands.add_parser("catalog", help="show compute and storage specifications and prices")
    _add_connection_arguments(catalog_parser, suppress_defaults=True)
    _add_format_argument(catalog_parser)

    storage = commands.add_parser("storage", help="read authorized storage observations")
    storage_commands = storage.add_subparsers(dest="storage_command", required=True)
    for command, help_text in (
        ("workspaces", "list workspaces where you may read storage observations"),
        ("quota-summary", "show sampled storage quota and usage"),
        ("native-quota", "read authorized Lustre quota subjects on demand"),
    ):
        quota_parser = storage_commands.add_parser(command, help=help_text)
        _add_connection_arguments(quota_parser, suppress_defaults=True)
        quota_parser.add_argument("--workspace-key", required=command != "workspaces", help="workspace key, such as personal:<id>")
        if command == "workspaces":
            quota_parser.add_argument("--limit", type=int, default=50, help="maximum rows in one page (1-100)")
            quota_parser.add_argument("--cursor", help="next cursor returned by the previous page")
        _add_format_argument(quota_parser)

    auth = commands.add_parser("auth", help="manage the SAI CLI device session")
    auth_commands = auth.add_subparsers(dest="auth_command", required=True)
    login_parser = auth_commands.add_parser(
        "login",
        help="authorize this user account once in a browser",
    )
    _add_connection_arguments(login_parser, suppress_defaults=True)
    login_parser.add_argument(
        "--no-wait",
        action="store_true",
        help="start device authorization and return; resume with --resume",
    )
    login_parser.add_argument(
        "--resume",
        action="store_true",
        help="resume the protected pending device authorization",
    )
    _add_format_argument(login_parser)

    status_parser = auth_commands.add_parser(
        "status",
        help="show the current CLI device session and account verification status",
    )
    _add_connection_arguments(status_parser, suppress_defaults=True)
    _add_format_argument(status_parser)

    logout_parser = auth_commands.add_parser(
        "logout",
        help="revoke the current CLI device session",
    )
    _add_connection_arguments(logout_parser, suppress_defaults=True)
    _add_format_argument(logout_parser)
    return parser


def _add_connection_arguments(parser: argparse.ArgumentParser, *, suppress_defaults: bool = False) -> None:
    default = argparse.SUPPRESS if suppress_defaults else None
    parser.add_argument("--config", default=default, help="TOML configuration path")
    parser.add_argument("--profile", default=default, help="configuration profile")
    parser.add_argument("--base-url", default=default, help="SAI API base URL")
    parser.add_argument("--site", default=default, help="SAI site identifier")
    parser.add_argument("--cluster", default=default, help="optional cluster identifier")
    parser.add_argument("--timeout", type=float, default=default, help="API timeout in seconds")
    parser.add_argument("--cache", default=default, help="short-lived token cache path")
    parser.add_argument(
        "--no-cache",
        action="store_true",
        default=default if suppress_defaults else False,
        help="do not read or write the token cache",
    )
    parser.add_argument(
        "--allow-insecure-http",
        action="store_true",
        default=default,
        help="allow plain HTTP for development",
    )


def _add_job_scope_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--scope",
        choices=("self", "personal-account", "org-account", "project-account"),
        help="authorized visibility scope (default: workspace kind, or self without a workspace)",
    )
    selector = parser.add_mutually_exclusive_group()
    selector.add_argument("--account", help="Portal compute account name")
    selector.add_argument("--account-id", help="Portal compute account ID")
    selector.add_argument("--workspace-key", help="compute read scope: personal:<id>, org:<id>, or project:<id>")
    parser.add_argument("--states", help="comma-separated state narrowing filter")


def _add_format_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--format",
        choices=("json", "table"),
        default="json",
        help="output format (default: json)",
    )


def _build_transport(settings: Settings) -> JsonTransport:
    return JsonTransport(
        base_url=settings.base_url,
        timeout_seconds=settings.timeout_seconds,
        allow_insecure_http=settings.allow_insecure_http,
    )


def _build_oidc_client(settings: Settings) -> OidcClient | None:
    issuer = (settings.identity_issuer or "").strip()
    if not issuer:
        return None
    try:
        parsed = urlsplit(issuer)
    except ValueError as exc:
        raise ContractError("the SAI Identity issuer is invalid") from exc
    if (
        parsed.scheme not in {"https", "http"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ContractError("the SAI Identity issuer is invalid")
    origin = urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
    identity_transport = JsonTransport(
        base_url=origin,
        timeout_seconds=settings.timeout_seconds,
        allow_insecure_http=settings.allow_insecure_http,
    )
    return OidcClient(
        transport=identity_transport,
        issuer_url=issuer.rstrip("/"),
        client_id=settings.oidc_client_id,
        scope=settings.oidc_scope,
        resource=settings.oidc_resource,
    )


def _auth_result_output(
    payload: Mapping[str, object],
    *,
    output_format: str,
    output: TextIO,
) -> None:
    if output_format == "json":
        output.write(json.dumps(dict(payload), ensure_ascii=False, sort_keys=True) + "\n")
        return
    for key, value in payload.items():
        output.write(f"{key}: {value}\n")


def _poll_device_authorization(
    *,
    provider: TokenProvider,
    oidc_client: OidcClient,
    authorization: DeviceAuthorization | None,
    device_code: str,
    interval_seconds: int,
    output: TextIO,
) -> dict[str, object]:
    now = int(provider.clock())
    deadline = authorization.expires_at if authorization is not None else now + 600
    interval = max(1, min(30, int(interval_seconds)))
    while now < deadline:
        try:
            result = oidc_client.poll_device_token(device_code=device_code, now=now)
        except OidcPending:
            result = None
        except OidcSlowDown:
            interval = min(30, interval + 5)
            result = None
        if result is not None:
            provider.install_device_tokens(result)
            provider.clear_pending_device_code()
            return {
                "ok": True,
                "authenticated": True,
                "subject": result.subject,
                "device_id": result.device_id,
                "expires_at": result.access_expires_at,
                "refresh_expires_at": result.refresh_expires_at,
            }
        if authorization is None:
            deadline = min(deadline, now + 600)
        remaining = deadline - now
        if remaining <= 0:
            break
        output.write("等待浏览器确认 CLI 登录...\n")
        output.flush()
        time.sleep(min(interval, remaining))
        now = int(provider.clock())
    raise AuthenticationError(
        "device authorization expired; run `sai auth login` again",
        code="credentials_unavailable",
    )


def _handle_auth_command(
    args: argparse.Namespace,
    *,
    oidc_client: OidcClient | None,
    provider: TokenProvider,
    output: TextIO,
    errors: TextIO,
) -> int:
    output_format = getattr(args, "format", "json")
    if args.auth_command == "login":
        if oidc_client is None:
            raise AuthenticationError(
                "SAI Identity issuer is not configured; set identity_issuer in the profile",
                code="credentials_unavailable",
            )
        if args.no_wait and args.resume:
            raise ContractError("use either --no-wait or --resume")
        authorization: DeviceAuthorization | None = None
        if args.resume:
            pending = provider.pending_device_code()
            if not pending:
                raise AuthenticationError(
                    "no pending device authorization; run `sai auth login`",
                    code="credentials_unavailable",
                )
            device_code, expires_at = pending
            authorization = DeviceAuthorization(
                device_code=device_code,
                user_code="",
                verification_url="",
                expires_at=expires_at,
                interval_seconds=5,
            )
        else:
            authorization = provider.start_device_authorization()
            errors.write(
                "请在浏览器打开以下地址，并确认显示的设备码：\n"
                f"{authorization.verification_url}\n"
                f"设备码：{authorization.user_code}\n"
            )
        if args.no_wait:
            return_value = {
                "ok": True,
                "status": "pending",
                "verification_url": authorization.verification_url,
                "user_code": authorization.user_code,
                "expires_at": authorization.expires_at,
                "interval_seconds": authorization.interval_seconds,
                "resume": "sai auth login --resume",
            }
            _auth_result_output(return_value, output_format=output_format, output=output)
            return 0
        result = _poll_device_authorization(
            provider=provider,
            oidc_client=oidc_client,
            authorization=authorization,
            device_code=authorization.device_code,
            interval_seconds=authorization.interval_seconds,
            output=errors,
        )
        _auth_result_output(result, output_format=output_format, output=output)
        return 0

    if args.auth_command == "status":
        lease = provider.get()
        if oidc_client is None:
            if output_format == "table":
                output.write("凭据已读取，当前连接不支持账号认证状态查询。\n"
                             f"认证入口：{urljoin(provider.transport.base_url, ACCOUNT_VERIFICATION_PATH)}\n")
                return 0
            _auth_result_output(
                {
                    "ok": True,
                    "authenticated": True,
                    "source": lease.source,
                    "access_expires_at": lease.expires_at,
                    "refresh_expires_at": None,
                },
                output_format=output_format,
                output=output,
            )
            return 0
        refresh = provider.device_refresh()
        safe = {
            "ok": True,
            "authenticated": True,
            "source": lease.source,
            "issuer": oidc_client.issuer_url,
            "client_id": oidc_client.client_id,
            "access_expires_at": lease.expires_at,
            "refresh_expires_at": refresh[1] if refresh else None,
        }
        account = PortalClient(transport=provider.transport, token_provider=provider).account_status(lease=lease)
        if output_format == "json":
            safe["account"] = account.as_dict()
            _auth_result_output(safe, output_format=output_format, output=output)
        else:
            output.write(render_account_status(account))
        return 0

    if args.auth_command == "logout":
        server_revoked = provider.revoke_device()
        _auth_result_output(
            {"ok": True, "revoked": server_revoked, "local_cleared": True},
            output_format=output_format,
            output=output,
        )
        return 0

    raise ContractError("the selected auth command is not implemented")


def _job_query(args: argparse.Namespace, *, settings: Settings) -> JobQuery:
    from .managed_runs import clean_tasks_workspace
    workspace = clean_tasks_workspace(args.workspace_key) if args.workspace_key is not None else None
    return JobQuery(
        site_id=settings.site_id,
        scope=args.scope or (workspace.split(":", 1)[0] + "-account" if workspace is not None else "self"),
        cluster_id=getattr(args, "cluster", None) or settings.cluster_id,
        account_name=args.account,
        account_id=args.account_id,
        states=clean_states(args.states),
        partition=getattr(args, "partition", None),
        limit=getattr(args, "limit", 100),
        workspace_key=workspace,
    )


def _emit_error(error: SaiCliError, *, output_format: str, stderr: TextIO) -> None:
    if output_format == "json":
        stderr.write(json.dumps(error.as_dict(), ensure_ascii=False) + "\n")
        return
    suffix = f" (request {error.request_id})" if error.request_id else ""
    stderr.write(f"ERROR [{error.code}]: {error.message}{suffix}\n")


def _load_overview_console() -> type:
    try:
        from rich.console import Console
    except ModuleNotFoundError as exc:
        if exc.name != "rich":
            raise
        raise ConfigError("Terminal UI dependencies are unavailable; install sai-cli[tui].") from None
    return Console


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    output = sys.stdout if stdout is None else stdout
    errors = sys.stderr if stderr is None else stderr
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    output_format = getattr(args, "format", "json")
    env = os.environ if environ is None else environ

    try:
        settings = resolve_settings(args, env)
        transport = _build_transport(settings)
        oidc_client = _build_oidc_client(settings)
        provider = TokenProvider(
            settings=settings,
            transport=transport,
            environ=env,
            oidc_client=oidc_client,
        )
        if args.command == "auth":
            return _handle_auth_command(
                args,
                oidc_client=oidc_client,
                provider=provider,
                output=output,
                errors=errors,
            )
        capability_provider = (
            CapabilityProvider(
                settings=settings,
                portal_transport=transport,
            )
            if settings.require_site_capability
            else None
        )
        client = PortalClient(
            transport=transport,
            token_provider=provider,
            capability_provider=capability_provider,
            site_transport=(
                JsonTransport(base_url=settings.site_read_base_url, timeout_seconds=settings.timeout_seconds)
                if settings.site_read_base_url else None
            ),
        )
        login_account = env.get("_SAI_LOGIN_ACCOUNT") if settings.managed_login_node else None
        if args.command == "status":
            if args.cluster is not None:
                raise ConfigError("status is site-scoped and does not accept --cluster")
            account = args.account if args.account is not None else login_account
            if output_format == "tui":
                from concurrent.futures import ThreadPoolExecutor
                from .overview_view import overview_panel
                with ThreadPoolExecutor(max_workers=1) as worker:
                    loading = worker.submit(_load_overview_console)
                    result = client.account_overview(settings.site_id, account=account)
                    console = loading.result()
                console(file=output).print(overview_panel(result, work_dir=os.getcwd(), base_url=settings.base_url,
                                                        language=args.language))
                return 0
            result = client.account_overview(settings.site_id, account=account)
            if output_format == "json":
                output.write(render_json(result.as_dict()))
            else:
                output.write(render_overview(result, work_dir=os.getcwd(), language=args.language))
            return 0
        if args.command == "resources":
            if args.cluster is not None:
                raise ConfigError("resources catalog is site-scoped and does not accept --cluster")
            catalog = client.resource_catalog(settings.site_id)
            output.write(render_json(catalog.as_dict()) if output_format == "json" else render_resource_catalog(catalog))
            return 0
        if args.command == "storage":
            if args.cluster is not None:
                raise ConfigError("storage reads are site-scoped and do not accept --cluster")
            if args.storage_command == "workspaces":
                result = client.list_storage_workspaces(site_id=settings.site_id, limit=args.limit,
                                                       cursor=args.cursor, workspace_key=args.workspace_key)
                rendered = render_storage_workspaces
            elif args.storage_command == "native-quota":
                result = client.storage_native_quota(workspace_key=args.workspace_key, site_id=settings.site_id)
                rendered = render_native_quota
            else:
                result = client.storage_quota_summary(workspace_key=args.workspace_key, site_id=settings.site_id)
                rendered = render_storage_quota_summary
            output.write(render_json(result.as_dict()) if output_format == "json" else rendered(result))
            return 0
        if args.command == "runs":
            from .managed_runs import render_managed_runs
            if args.cluster is not None:
                raise ConfigError("managed runs are site-scoped and do not accept --cluster")
            scope = {"workspace_key": getattr(args, "workspace_key", None), "site_id": settings.site_id}
            if args.runs_command == "workspaces":
                result = client.list_run_workspaces(site_id=settings.site_id, limit=args.limit,
                                                   cursor=args.cursor, workspace_key=args.workspace_key)
            elif args.runs_command == "recent":
                result = client.list_my_managed_runs(site_id=settings.site_id, limit=args.limit, cursor=args.cursor)
            elif args.runs_command == "list":
                result = client.list_managed_runs(**scope, limit=args.limit, cursor=args.cursor)
            elif args.runs_command == "show":
                result = client.managed_run(args.run_ref, **scope)
            elif args.runs_command == "cost":
                from .run_cost import render_run_cost
                result = client.managed_run_cost(args.run_ref, **scope)
            elif args.runs_command == "placement":
                from .run_placement import render_run_placement
                result = client.managed_run_placement(args.run_ref, **scope)
            elif args.runs_command == "stats":
                from .run_stats import render_run_stats
                result = client.managed_run_stats(args.run_ref, **scope)
            elif args.runs_command == "read":
                from .artifact_content import render_artifact_content
                result = client.managed_run_artifact_content(args.run_ref, **scope, artifact_ref=args.artifact_ref,
                    artifact_cursor=args.artifact_cursor, cursor=args.cursor)
            elif args.runs_command == "download":
                receipt = client.download_managed_run_artifact(args.run_ref, **scope, artifact_ref=args.artifact_ref,
                    artifact_cursor=args.artifact_cursor, output=args.output)
                from .managed_runs import terminal_log
                output.write(render_json(receipt) if output_format == "json" else
                    f"Saved {receipt['size_bytes']} bytes to {terminal_log(receipt['output'])}\n")
                return 0
            elif args.runs_command == "logs":
                result = client.managed_run_logs(args.run_ref, **scope, stream=args.stream,
                                                 cursor=args.cursor, max_bytes=args.max_bytes)
            else:
                result = client.managed_run_artifacts(args.run_ref, **scope, cursor=args.cursor, limit=args.limit)
            render = (render_artifact_content if args.runs_command == "read" else render_run_cost if args.runs_command == "cost" else
                      render_run_stats if args.runs_command == "stats" else
                      render_run_placement if args.runs_command == "placement" else render_managed_runs)
            output.write(render_json(result.as_dict()) if output_format == "json" else render(result))
            return 0
        query = _job_query(args, settings=settings)

        if args.command == "jobs" and args.jobs_command == "list":
            result = client.list_jobs(query)
        elif args.command == "jobs" and args.jobs_command == "show":
            result = client.show_job(args.job_id, query)
        elif args.command == "jobs" and args.jobs_command == "allocation":
            result = client.job_allocation(args.job_id, query)
        elif args.command == "jobs" and args.jobs_command == "placement":
            result = client.job_placement(args.job_id, query)
        elif args.command == "jobs" and args.jobs_command == "cost":
            result = client.running_estimates(query)
        else:
            raise ContractError("the selected command is not implemented")

        if output_format == "json":
            output.write(render_json(result.as_dict()))
        elif args.jobs_command == "cost":
            width = shutil.get_terminal_size().columns if output.isatty() else 80
            output.write(render_running_estimate_table(result, width=width))
        elif isinstance(result, SiteJobPlacementResult):
            output.write(render_site_placement(result))
        elif isinstance(result, SiteJobAllocationResult):
            output.write(render_site_allocation(result))
        elif isinstance(result, SiteJobResult):
            output.write(render_site_jobs(result))
        else:
            output.write(render_table(result))
        return 0
    except SaiCliError as exc:
        if (args.command == "auth" and args.auth_command == "status"
                and output_format == "table" and isinstance(exc, AuthenticationError)
                and (exc.code == "credentials_unavailable" or exc.request_id is not None)):
            errors.write("请运行 sai auth login 完成 CLI 登录。\n"
                         f"身份认证：{urljoin(transport.base_url, ACCOUNT_VERIFICATION_PATH)}\n")
        else:
            _emit_error(exc, output_format=output_format, stderr=errors)
        return exc.exit_code
    except KeyboardInterrupt:
        interrupted = SaiCliError(code="interrupted", message="operation interrupted", exit_code=130)
        _emit_error(interrupted, output_format=output_format, stderr=errors)
        return interrupted.exit_code
    except Exception:
        internal = ContractError("the client encountered an internal error", code="internal_error")
        _emit_error(internal, output_format=output_format, stderr=errors)
        return internal.exit_code


def entrypoint() -> None:
    raise SystemExit(main())
