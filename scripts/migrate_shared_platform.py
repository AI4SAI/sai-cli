#!/usr/bin/env python3
"""Replace existing site-runtime mounts with one shared platform mount."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile

PATHS = {"envs": "envs", "sai_config": "runtime", "sbatch_examples": "examples", "slurm": "slurm"}


def command(*args: str) -> str:
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=30).stdout.strip()


def atomic_write(path: Path, content: str) -> None:
    fd, temporary = tempfile.mkstemp(prefix=".sai-platform-", dir=path.parent)
    with os.fdopen(fd, "w") as output:
        output.write(content)
        output.flush()
        os.fchmod(output.fileno(), 0o644)
        os.fsync(output.fileno())
    os.replace(temporary, path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--rollback", action="store_true")
    parser.add_argument("--node-package", type=Path)
    parser.add_argument("--config", type=Path)
    args = parser.parse_args()
    assert not (args.apply and args.rollback)
    assert os.geteuid() == 0 and sys.version_info >= (3, 11)
    os.umask(0o022)
    fstab = Path("/etc/fstab")
    checkpoint = Path("/var/lib/sai-platform-migration")
    target = Path("/opt/sai")
    originals = {}
    before = fstab.read_text()
    for line in before.splitlines():
        fields = line.split()
        if len(fields) >= 4 and not fields[0].startswith("#"):
            for name in PATHS:
                if fields[1] == f"/opt/{name}":
                    assert name not in originals and fields[2] in ("nfs", "nfs4")
                    assert fields[0].endswith(f":/opt/{name}")
                    originals[name] = fields
    state_path = checkpoint / "state.json"

    def restore(state: dict) -> None:
        for name in reversed(state["converted"]):
            path = Path("/opt") / name
            assert path.is_symlink() and os.readlink(path) == f"/opt/sai/{PATHS[name]}"
            path.unlink()
            shadow = checkpoint / ("under-mount-" + name)
            if shadow.exists(): shadow.rename(path)
            else: path.mkdir(mode=0o755)
            source, _, fstype, options = state["originals"][name][:4]
            command("mount", "-t", fstype, "-o", options, source, str(path))
        atomic_write(fstab, (checkpoint / "fstab.before").read_text())
        command("systemctl", "daemon-reload")
        command("umount", str(target))
        state["restored"] = True
        state_path.write_text(json.dumps(state, indent=2) + "\n")

    if args.rollback:
        restore(json.loads(state_path.read_text()))
        print("restored previous mounts; restore a previous node package separately if needed")
        return
    assert set(originals) == set(PATHS), "not the standard four-mount site layout"
    sources = {fields[0].rsplit(":", 1)[0] for fields in originals.values()}
    assert len(sources) == 1
    source = sources.pop() + ":/opt/sai"
    reference = originals["envs"]
    for name in PATHS:
        path = Path("/opt") / name
        assert not path.is_symlink()
        assert command("findmnt", "-rn", "-M", str(path), "-o", "FSTYPE") in ("nfs", "nfs4")
    print(json.dumps({"host": socket.gethostname(), "source": source, "replace": list(originals), "apply": args.apply}))
    if not args.apply: return
    assert not state_path.exists(), "an existing migration checkpoint must be reviewed"
    assert not target.is_symlink() and (not target.exists() or not any(target.iterdir()))
    checkpoint.mkdir(mode=0o700, parents=True, exist_ok=True)
    (checkpoint / "fstab.before").write_text(before)
    target.mkdir(mode=0o755, exist_ok=True)
    command("mount", "-t", reference[2], "-o", reference[3], source, str(target))
    state = {"originals": originals, "converted": [], "source": source}
    try:
        assert (target / "shell/bash.profile").is_file()
        assert (target / "bin/sai").is_file()
        assert command(str(target / "bin/sai"), "--version").startswith("sai ")
        for name, destination in PATHS.items():
            path = Path("/opt") / name
            command("umount", str(path))
            shadow = checkpoint / ("under-mount-" + name)
            if any(path.iterdir()): path.rename(shadow)
            else: path.rmdir()
            path.symlink_to(target / destination)
            state["converted"].append(name)
            state_path.write_text(json.dumps(state, indent=2) + "\n")
        lines = [line for line in before.splitlines() if not (
            len(line.split()) >= 2 and line.split()[1] in {f"/opt/{name}" for name in PATHS}
        )]
        lines.append(f"{source} /opt/sai {reference[2]} {reference[3]} 0 0")
        atomic_write(fstab, "\n".join(lines) + "\n")
        prior_dropin = Path("/etc/systemd/system/opt-envs.mount.d/10-sai-nfs-rdma-ready.conf")
        if prior_dropin.exists():
            next_dropin = Path("/etc/systemd/system/opt-sai.mount.d/10-sai-nfs-rdma-ready.conf")
            next_dropin.parent.mkdir(mode=0o755, exist_ok=True)
            shutil.copyfile(prior_dropin, next_dropin)
        command("systemctl", "daemon-reload")
        command("scontrol", "ping")
    except Exception:
        restore(state)
        raise
    if args.config and not Path("/etc/sai-cli/config.toml").exists():
        Path("/etc/sai-cli").mkdir(mode=0o755, exist_ok=True)
        shutil.copyfile(args.config, "/etc/sai-cli/config.toml")
        Path("/etc/sai-cli/config.toml").chmod(0o644)
    if args.node_package:
        command("dpkg", "-i", str(args.node_package))
        command("/usr/bin/sai", "--version")
    state["complete"] = True
    state_path.write_text(json.dumps(state, indent=2) + "\n")
    print(json.dumps({"host": socket.gethostname(), "complete": True, "checkpoint": str(checkpoint)}))


if __name__ == "__main__":
    main()
