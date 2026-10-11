"""The Agent guidance shipped with this CLI, available without any service."""

from importlib.resources import files

from . import __version__


def bundled_skill() -> dict[str, str]:
    content = files("sai_cli").joinpath("skills", "sai-cli", "SKILL.md").read_text(encoding="utf-8")
    return {"schema_version": "cli.skill/v1", "client_version": __version__,
            "name": "sai-cli", "content": content}
