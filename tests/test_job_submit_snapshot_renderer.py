from __future__ import annotations

import json
from pathlib import Path
import stat
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
RENDERER = ROOT / "scripts" / "render_job_submit_snapshot.py"


def _valid_projection() -> dict:
    return {
        "schema_version": 1,
        "revision": "projection-42",
        "generated_at": 100,
        "expires_at": 200,
        "gpu_policy": {"per_node_multiple": 4, "exempt_qos": ["z-qos", "a-qos", "a-qos"]},
        "personal_accounts": {"zoe": "personal-zoe", "alice": "personal-alice"},
        "org_accounts": {"org-example": "account-example"},
        "project_accounts": {
            "org-example/proj-standard": "account-example",
            "org-example/proj-research": "project-example",
        },
        "home_aliases": {"alice/workdir_org-example": "org-example"},
    }


def _run(tmp_path: Path, payload: dict) -> subprocess.CompletedProcess[str]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    source = tmp_path / "projection.json"
    output = tmp_path / "snapshot.lua"
    source.write_text(json.dumps(payload), encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(RENDERER), "--input", str(source), "--output", str(output)],
        capture_output=True,
        text=True,
    )


def test_renderer_is_deterministic_atomic_and_sorted(tmp_path: Path) -> None:
    completed = _run(tmp_path, _valid_projection())
    assert completed.returncode == 0, completed.stderr
    output = tmp_path / "snapshot.lua"
    text = output.read_text(encoding="utf-8")

    assert text.startswith("return {\n")
    assert text.count('["a-qos"] = true') == 1
    assert text.index('["alice"]') < text.index('["zoe"]')
    assert stat.S_IMODE(output.stat().st_mode) == 0o644
    assert not list(tmp_path.glob(".snapshot.lua.*"))


def test_renderer_rejects_unknown_fields_and_lua_injection(tmp_path: Path) -> None:
    unknown = _valid_projection()
    unknown["extra"] = True
    completed = _run(tmp_path / "unknown", unknown)
    assert completed.returncode != 0
    assert "fields do not match" in completed.stderr

    injected = _valid_projection()
    injected["personal_accounts"] = {'alice"] = os.execute("bad") --': "personal-alice"}
    completed = _run(tmp_path / "injected", injected)
    assert completed.returncode != 0
    assert "canonical token" in completed.stderr


def test_renderer_requires_known_orgs_for_projects_and_aliases(tmp_path: Path) -> None:
    payload = _valid_projection()
    payload["project_accounts"] = {"org-missing/proj-x": "proj-x"}
    completed = _run(tmp_path / "project", payload)
    assert completed.returncode != 0
    assert "unknown org" in completed.stderr

    payload = _valid_projection()
    payload["home_aliases"] = {"alice/workdir_org-missing": "org-missing"}
    completed = _run(tmp_path / "alias", payload)
    assert completed.returncode != 0
    assert "not a provisioned org alias" in completed.stderr
