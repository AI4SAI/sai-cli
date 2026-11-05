#!/usr/bin/env python3
"""Export the canonical Portal readers into the standalone CLI package.

There is no independent client implementation. The source digest is checked in
CI; paired source validation additionally compares the export to its producer.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
EXPORTS = (
    ("sai_native_slurm.py", "native-slurm-source.json"),
    ("sai_compute_restrictions.py", "compute-restrictions-source.json"),
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, help="canonical sai-portal checkout")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for name, pin_name in EXPORTS:
        target = ROOT / "src" / name
        manifest = ROOT / "contracts" / pin_name
        if args.source:
            content = (args.source / name).read_bytes()
            revision = subprocess.check_output(
                ["git", "-C", str(args.source), "rev-parse", "HEAD"], text=True).strip()
            committed = subprocess.check_output(["git", "-C", str(args.source), "show", f"{revision}:{name}"])
            if content != committed:
                raise SystemExit("canonical reader must match its recorded source commit")
            pin = {"repository": "AI4SAI/sai-portal", "path": name, "revision": revision,
                   "sha256": hashlib.sha256(content).hexdigest()}
            if not args.check:
                target.write_bytes(content)
                manifest.write_text(json.dumps(pin, indent=2) + "\n")
        else:
            content = target.read_bytes()
        if target.read_bytes() != content or hashlib.sha256(content).hexdigest() != json.loads(manifest.read_text())["sha256"]:
            raise SystemExit("reader export differs from its canonical source")


if __name__ == "__main__":
    main()
