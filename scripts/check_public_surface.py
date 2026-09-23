#!/usr/bin/env python3
"""Fail when candidate public files contain common private-data patterns."""

from __future__ import annotations

import re
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SELF = Path(__file__).resolve()
TEXT_SUFFIXES = {
    "",
    ".bash",
    ".cfg",
    ".html",
    ".ini",
    ".json",
    ".lua",
    ".md",
    ".py",
    ".sh",
    ".tcl",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
PATTERNS = {
    "private IPv4 address": re.compile(
        r"(?<!\d)(?:10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2})(?!\d)"
    ),
    "absolute user or temporary path": re.compile(r"(?<![A-Za-z0-9_])/(?:home|tmp)/(?!<)[^\s)`'\"]+"),
    "private key material": re.compile(r"-----BEGIN (?:OPENSSH|RSA|EC|DSA) PRIVATE KEY-----"),
    "credential assignment": re.compile(
        r"(?i)\b(?:password|passwd|shared_secret|client_secret|api_key|access_token)\b\s*[:=]\s*[\"'](?!redacted|example|placeholder)[^\"']+[\"']"
    ),
}


def candidate_files() -> list[Path]:
    completed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    paths = []
    for raw in completed.stdout.split(b"\0"):
        if not raw:
            continue
        path = ROOT / raw.decode("utf-8")
        if path.resolve() == SELF or path.suffix.lower() not in TEXT_SUFFIXES or not path.is_file():
            continue
        paths.append(path)
    return paths


def main() -> int:
    findings: list[str] = []
    for path in candidate_files():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            if "public-scan: allow-test-vector" in line and path.is_relative_to(ROOT / "tests"):
                continue
            for label, pattern in PATTERNS.items():
                if pattern.search(line):
                    findings.append(f"{path.relative_to(ROOT)}:{line_number}: {label}")
    if findings:
        print("public-surface scan failed:", file=sys.stderr)
        print("\n".join(findings), file=sys.stderr)
        return 1
    print(f"public-surface scan passed ({len(candidate_files())} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
