#!/usr/bin/env python3
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

import openpyxl


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "SUBTLEX-NL with pos and Zipf.xlsx"
OUTPUT = ROOT / "outputs" / "subtlex_reference_profile.json"


def main() -> None:
    workbook = openpyxl.load_workbook(REFERENCE, read_only=True, data_only=True)
    worksheet = workbook.active
    rows = worksheet.iter_rows(values_only=True)
    headers = list(next(rows))
    idx = {header: position for position, header in enumerate(headers)}

    data_rows = 0
    total_freq = 0
    max_cd = 0
    formula_samples = []

    for row in rows:
        data_rows += 1
        freq = int(row[idx["FREQcount"]] or 0)
        cd = int(row[idx["CDcount"]] or 0)
        total_freq += freq
        max_cd = max(max_cd, cd)
        if len(formula_samples) < 10 and freq > 0 and cd > 0:
            formula_samples.append(
                {
                    "Word": row[idx["Word"]],
                    "FREQcount": freq,
                    "CDcount": cd,
                    "SUBTLEXWF": row[idx["SUBTLEXWF"]],
                    "Zipf": row[idx["Zipf"]],
                    "SUBTLEXCD": row[idx["SUBTLEXCD"]],
                    "Lg10CD": row[idx["Lg10CD"]],
                }
            )

    for sample in formula_samples:
        freq = sample["FREQcount"]
        cd = sample["CDcount"]
        sample["computed_SUBTLEXWF"] = freq / total_freq * 1_000_000
        sample["computed_Zipf"] = math.log10(freq / total_freq * 1_000_000_000)
        sample["computed_SUBTLEXCD"] = cd / max_cd * 100
        sample["computed_Lg10CD"] = math.log10(cd)

    profile = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "reference": str(REFERENCE),
        "sheet": worksheet.title,
        "headers": headers,
        "data_rows": data_rows,
        "total_FREQcount": total_freq,
        "max_CDcount": max_cd,
        "formula_samples": formula_samples,
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()

