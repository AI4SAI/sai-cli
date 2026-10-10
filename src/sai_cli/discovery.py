"""Offline operation discovery from the actual argparse command tree."""
from __future__ import annotations

import argparse
from typing import Any

from . import __version__
from .errors import ConfigError


_CONNECTION = {"config", "profile", "base_url", "site", "cluster", "timeout", "cache", "no_cache", "allow_insecure_http"}


def _children(parser: argparse.ArgumentParser) -> dict[str, tuple[argparse.ArgumentParser, str]]:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            summaries = {item.dest: item.help for item in action._choices_actions}
            return {name: (child, summaries[name]) for name, child in action.choices.items()}
    return {}


def _leaves(parser: argparse.ArgumentParser, path: tuple[str, ...] = (), summary: str = ""):
    children = _children(parser)
    if not children:
        yield path, summary, parser
    for name, (child, help_text) in children.items():
        yield from _leaves(child, (*path, name), help_text)


def _parameter(action: argparse.Action, *, default: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "name": action.dest, "flags": action.option_strings,
        "type": "boolean" if action.nargs == 0 else "integer" if action.type is int else "number" if action.type is float else "string",
        "arity": 1 if action.nargs is None else action.nargs,
        "required": action.required, "description": action.help or "",
    }
    if default != argparse.SUPPRESS:
        value["default"] = default
    if action.choices is not None:
        value["choices"] = list(action.choices)
    return value


def _parameters(parser: argparse.ArgumentParser, root: argparse.ArgumentParser, operation: dict) -> list[dict]:
    actions = {action.dest: action for action in root._actions if action.dest in _CONNECTION}
    actions.update({action.dest: action for action in parser._actions
                    if not isinstance(action, (argparse._HelpAction, argparse._VersionAction))})
    allowed = _CONNECTION - {"site", "cluster"} if operation["source"] not in {"native", "client"} else {"timeout"}
    if operation["site_option"]:
        allowed |= {"site"}
    if operation["cluster_option"]:
        allowed |= {"cluster"}
    if operation["source"] == "client":
        allowed = set()
    return [_parameter(action, default=(root.get_default(name) if action.default == argparse.SUPPRESS else parser.get_default(name)))
            for name, action in actions.items() if name not in _CONNECTION or name in allowed]


def describe(root: argparse.ArgumentParser, path: list[str]) -> dict[str, Any]:
    selected, summary = root, ""
    for word in path:
        entry = _children(selected).get(word)
        if entry is None:
            raise ConfigError("Unknown command path; use sai describe to list operations.", code="command_not_found")
        selected, summary = entry
    detailed = not _children(selected)
    operations = []
    for words, help_text, parser in _leaves(selected, tuple(path), summary):
        metadata = parser.get_default("_operation")
        if metadata is None:
            raise RuntimeError("Command registration is missing operation metadata")
        operation = {"command": list(words), "summary": help_text,
                     **(metadata if detailed else {key: metadata[key] for key in ("source", "effect", "interaction")})}
        if detailed:
            operation["parameters"] = _parameters(parser, root, metadata)
            operation["exclusive_parameters"] = [
                {"parameters": [action.dest for action in group._group_actions], "required": group.required}
                for group in parser._mutually_exclusive_groups
            ]
        operations.append(operation)
    return {"schema_version": "cli.describe/v1", "client_version": __version__,
            "authorization_checked": False, "path": path, "detailed": detailed, "operations": operations}


def render_description(value: dict) -> str:
    lines = []
    for operation in value["operations"]:
        lines.append(f"sai {' '.join(operation['command'])}  [{operation['effect']}; {operation['source']}]")
        lines.append("  " + operation["summary"])
        for parameter in operation.get("parameters", []):
            name = ", ".join(parameter["flags"]) or parameter["name"]
            lines.append(f"  {name}: {parameter['type']}" + (" (required)" if parameter["required"] else ""))
    return "\n".join(lines) + "\n"
