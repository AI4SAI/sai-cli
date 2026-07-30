"""Command-line parser and stable process behavior."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Mapping, Sequence, TextIO

from . import __version__
from .auth import TokenProvider
from .client import JobQuery, PortalClient, clean_states
from .config import resolve_settings
from .errors import ContractError, SaiCliError
from .render import render_json, render_table
from .transport import JsonTransport


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sai",
        description="Read-only command-line client for SAI compute services",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    _add_connection_arguments(parser)

    commands = parser.add_subparsers(dest="command", required=True)
    jobs = commands.add_parser("jobs", help="read authorized scheduler jobs")
    job_commands = jobs.add_subparsers(dest="jobs_command", required=True)

    list_parser = job_commands.add_parser("list", help="list jobs in an authorized scope")
    _add_connection_arguments(list_parser, suppress_defaults=True)
    _add_job_scope_arguments(list_parser)
    list_parser.add_argument("--partition", help="partition narrowing filter")
    list_parser.add_argument("--limit", type=int, default=100, help="maximum jobs (1-500)")
    _add_format_argument(list_parser)

    show_parser = job_commands.add_parser("show", help="show one authorized job")
    _add_connection_arguments(show_parser, suppress_defaults=True)
    show_parser.add_argument("job_id", help="job identifier")
    _add_job_scope_arguments(show_parser)
    _add_format_argument(show_parser)
    return parser


def _add_connection_arguments(parser: argparse.ArgumentParser, *, suppress_defaults: bool = False) -> None:
    default = argparse.SUPPRESS if suppress_defaults else None
    parser.add_argument("--config", default=default, help="TOML configuration path")
    parser.add_argument("--profile", default=default, help="configuration profile")
    parser.add_argument("--base-url", default=default, help="SAI API base URL")
    parser.add_argument("--site", default=default, help="SAI site identifier")
    parser.add_argument("--username", default=default, help="username for managed-node token exchange")
    parser.add_argument("--key-id", default=default, help="key identifier for managed-node token exchange")
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
        default="self",
        help="authorized visibility scope",
    )
    selector = parser.add_mutually_exclusive_group()
    selector.add_argument("--account", help="Portal compute account name")
    selector.add_argument("--account-id", help="Portal compute account ID")
    parser.add_argument("--cluster", help="optional cluster identifier")
    parser.add_argument("--states", help="comma-separated state narrowing filter")


def _add_format_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--format",
        choices=("json", "table"),
        default="json",
        help="output format (default: json)",
    )


def _job_query(args: argparse.Namespace, *, site_id: str) -> JobQuery:
    return JobQuery(
        site_id=site_id,
        scope=args.scope,
        cluster_id=args.cluster,
        account_name=args.account,
        account_id=args.account_id,
        states=clean_states(args.states),
        partition=getattr(args, "partition", None),
        limit=getattr(args, "limit", 100),
    )


def _emit_error(error: SaiCliError, *, output_format: str, stderr: TextIO) -> None:
    if output_format == "json":
        stderr.write(json.dumps(error.as_dict(), ensure_ascii=False) + "\n")
        return
    suffix = f" (request {error.request_id})" if error.request_id else ""
    stderr.write(f"ERROR [{error.code}]: {error.message}{suffix}\n")


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
        transport = JsonTransport(
            base_url=settings.base_url,
            timeout_seconds=settings.timeout_seconds,
            allow_insecure_http=settings.allow_insecure_http,
        )
        provider = TokenProvider(settings=settings, transport=transport, environ=env)
        client = PortalClient(transport=transport, token_provider=provider)
        query = _job_query(args, site_id=settings.site_id)

        if args.command == "jobs" and args.jobs_command == "list":
            result = client.list_jobs(query)
        elif args.command == "jobs" and args.jobs_command == "show":
            result = client.show_job(args.job_id, query)
        else:
            raise ContractError("the selected command is not implemented")

        output.write(render_json(result.as_dict()) if output_format == "json" else render_table(result))
        return 0
    except SaiCliError as exc:
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
