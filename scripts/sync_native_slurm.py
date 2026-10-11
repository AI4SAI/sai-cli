#!/usr/bin/env python3
"""Export the canonical Portal native reader into the standalone CLI package.

There is no independent client implementation. The source digest is checked in
CI; paired source validation additionally compares the export to its producer.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, help="canonical sai-portal checkout")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    target = ROOT / "src/sai_native_slurm.py"
    manifest = ROOT / "contracts/native-slurm-source.json"
    if args.source:
        content = (args.source / "sai_native_slurm.py").read_bytes()
        pin = {"repository": "AI4SAI/sai-portal", "path": "sai_native_slurm.py",
               "revision": subprocess.check_output(["git", "-C", str(args.source), "rev-parse", "HEAD"], text=True).strip(),
               "sha256": hashlib.sha256(content).hexdigest()}
        if not args.check:
            target.write_bytes(content)
            manifest.write_text(json.dumps(pin, indent=2) + "\n")
    else:
        content = target.read_bytes()
        pin = json.loads(manifest.read_text())
    if target.read_bytes() != content or hashlib.sha256(content).hexdigest() != json.loads(manifest.read_text())["sha256"]:
        raise SystemExit("native Slurm export differs from its canonical source")


if __name__ == "__main__":
    main()
