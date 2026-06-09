#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_JSON = ROOT / "outputs" / "frog_probe.json"
OUTPUT_TSV = ROOT / "outputs" / "frog_sample.tsv"

sys.path.insert(0, str(ROOT))

from cc100_subtlex.frog import parse_frog_line


SAMPLE_TEXT = "\n".join(
    [
        "Dit is een kleine test voor Frog.",
        "In '41 werd aan de stamkaart een inlegvel toegevoegd.",
        "Amsterdamse fietsers hebben opa's oude auto-ongeluk niet gezien.",
    ]
)


def run_command(args: list[str], timeout: int = 60) -> dict[str, object]:
    try:
        completed = subprocess.run(
            args,
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
        return {
            "returncode": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
        }
    except FileNotFoundError as exc:
        return {"returncode": None, "stdout": "", "stderr": str(exc)}
    except subprocess.TimeoutExpired as exc:
        return {
            "returncode": None,
            "stdout": (exc.stdout or "").strip() if isinstance(exc.stdout, str) else "",
            "stderr": f"timeout after {timeout}s",
        }


def docker_daemon_status() -> dict[str, object]:
    if not shutil.which("docker"):
        return {"available": False, "running": False, "details": "docker command not found"}
    info = run_command(["docker", "info", "--format", "{{json .ServerVersion}}"], timeout=15)
    return {
        "available": True,
        "running": info["returncode"] == 0,
        "details": info,
    }


def run_local_frog() -> dict[str, object]:
    if not shutil.which("frog"):
        return {"available": False, "tokens": []}

    with tempfile.TemporaryDirectory() as tmpdir:
        input_path = Path(tmpdir) / "sample.txt"
        output_path = Path(tmpdir) / "sample.frog.tsv"
        input_path.write_text(SAMPLE_TEXT + "\n", encoding="utf-8")
        command = ["frog", "-t", str(input_path), "-o", str(output_path)]
        result = run_command(command, timeout=120)
        tokens = []
        if output_path.exists():
            for line in output_path.read_text(encoding="utf-8", errors="replace").splitlines():
                token = parse_frog_line(line)
                if token is not None:
                    tokens.append(
                        {
                            "word": token.word,
                            "lemma": token.lemma,
                            "pos": token.pos,
                            "pos_head": token.pos_head,
                            "confidence": token.confidence,
                        }
                    )
        return {
            "available": True,
            "command": command,
            "command_result": result,
            "tokens": tokens,
        }


def write_sample_tsv(tokens: list[dict[str, object]]) -> None:
    with OUTPUT_TSV.open("w", encoding="utf-8", newline="") as handle:
        handle.write("word\tlemma\tpos\tpos_head\tconfidence\n")
        for token in tokens:
            handle.write(
                "\t".join(
                    [
                        str(token["word"]),
                        str(token["lemma"]),
                        str(token["pos"]),
                        str(token["pos_head"]),
                        "" if token["confidence"] is None else str(token["confidence"]),
                    ]
                )
                + "\n"
            )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--write-empty-sample",
        action="store_true",
        help="write frog_sample.tsv even when Frog is unavailable",
    )
    args = parser.parse_args()

    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)

    local = run_local_frog()
    if local["tokens"] or args.write_empty_sample:
        write_sample_tsv(local["tokens"])

    probe = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "sample_text": SAMPLE_TEXT,
        "commands": {
            "frog": shutil.which("frog"),
            "ucto": shutil.which("ucto"),
            "docker": shutil.which("docker"),
        },
        "local_frog": local,
        "docker": docker_daemon_status(),
        "notes": [
            "Homebrew did not provide frog or ucto on this machine during initial probing.",
            "If local Frog is unavailable, the preferred next route is LaMachine/Frog in Docker.",
        ],
    }
    OUTPUT_JSON.write_text(json.dumps(probe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT_JSON}")
    if local["tokens"] or args.write_empty_sample:
        print(f"Wrote {OUTPUT_TSV}")
    if not local["available"]:
        print("Local frog command is unavailable.")
    if not probe["docker"]["running"]:
        print("Docker command exists but daemon is not running.")


if __name__ == "__main__":
    main()

