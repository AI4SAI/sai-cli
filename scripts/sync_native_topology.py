#!/usr/bin/env python3
"""Export the canonical Portal topology parser into the standalone CLI."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "src" / "sai_native_topology.py"
MANIFEST = ROOT / "contracts" / "native-topology-source.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, help="canonical sai-portal checkout")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.source:
        content = (args.source / "sai_native_topology.py").read_bytes()
        pin = {
            "repository": "AI4SAI/sai-portal",
            "path": "sai_native_topology.py",
            "revision": subprocess.check_output(["git", "-C", str(args.source), "rev-parse", "HEAD"], text=True).strip(),
            "sha256": hashlib.sha256(content).hexdigest(),
        }
        if not args.check:
            TARGET.write_bytes(content)
            MANIFEST.write_text(json.dumps(pin, indent=2) + "\n")
    if not MANIFEST.exists():
        raise SystemExit("native topology source manifest is missing")
    manifest = json.loads(MANIFEST.read_text())
    if args.source and TARGET.read_bytes() != (args.source / "sai_native_topology.py").read_bytes():
        raise SystemExit("native topology export differs from its source")
    if hashlib.sha256(TARGET.read_bytes()).hexdigest() != manifest.get("sha256"):
        raise SystemExit("native topology export differs from its manifest")


if __name__ == "__main__":
    main()
