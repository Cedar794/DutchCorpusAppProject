#!/usr/bin/env python3
from __future__ import annotations

import json
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "outputs" / "environment_probe.json"
CORPUS = ROOT / "nl.txt.xz"
REFERENCE = ROOT / "SUBTLEX-NL with pos and Zipf.xlsx"


def run_command(args: list[str]) -> dict[str, object]:
    try:
        completed = subprocess.run(
            args,
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        return {
            "returncode": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
        }
    except FileNotFoundError as exc:
        return {"returncode": None, "stdout": "", "stderr": str(exc)}


def file_info(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"exists": False}
    stat = path.stat()
    return {
        "exists": True,
        "size_bytes": stat.st_size,
        "size_mib": stat.st_size / 1024 / 1024,
        "modified_utc": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
    }


def main() -> None:
    disk = shutil.disk_usage(ROOT)
    probe = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "root": str(ROOT),
        "python": {
            "executable": sys.executable,
            "version": sys.version,
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "platform": platform.platform(),
        },
        "disk": {
            "total_bytes": disk.total,
            "used_bytes": disk.used,
            "free_bytes": disk.free,
            "free_gib": disk.free / 1024 / 1024 / 1024,
        },
        "files": {
            "corpus": file_info(CORPUS),
            "reference": file_info(REFERENCE),
        },
        "tools": {
            "xz": shutil.which("xz"),
            "frog": shutil.which("frog"),
            "ucto": shutil.which("ucto"),
            "docker": shutil.which("docker"),
            "brew": shutil.which("brew"),
        },
        "commands": {
            "xz_list": run_command(["xz", "-lv", str(CORPUS)]) if CORPUS.exists() else None,
            "frog_version": run_command(["frog", "--version"]) if shutil.which("frog") else None,
            "ucto_version": run_command(["ucto", "-V"]) if shutil.which("ucto") else None,
            "docker_version": run_command(["docker", "--version"]) if shutil.which("docker") else None,
        },
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(probe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()

