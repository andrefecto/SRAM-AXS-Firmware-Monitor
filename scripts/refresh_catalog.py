#!/usr/bin/env python3
"""Refresh models.json from SRAM's model catalog.

Fetches https://nexus.quarqnet.com/api/v2/models/, filters to published
entries, dedupes by model_code (keeping the first representative), and
writes a compact models.json at the repo root.

A model_code may appear on many model_id variants that share firmware
(e.g. ED-FRC-D2 has 8 variants). We pick the smallest model_id as the
representative — empirically stable, and the firmware endpoint returns
the same payload for every variant of a shared code.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

CATALOG_URL = "https://nexus.quarqnet.com/api/v2/models/"
REPO_ROOT = Path(__file__).resolve().parent.parent
MODELS_PATH = REPO_ROOT / "models.json"


def fetch_catalog() -> list[dict]:
    req = urllib.request.Request(CATALOG_URL, headers={"User-Agent": "SRAM-AXS-Firmware-Monitor"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    if not isinstance(data, list):
        raise RuntimeError(f"catalog did not return a list: {type(data).__name__}")
    return data


def collapse(entries: list[dict]) -> list[dict]:
    by_code: dict[str, dict] = {}
    for m in entries:
        code = m.get("model_code")
        if not code or not m.get("published"):
            continue
        existing = by_code.get(code)
        if existing is None or m["model_id"] < existing["model_id"]:
            by_code[code] = m

    out = []
    for code in sorted(by_code):
        m = by_code[code]
        out.append({
            "model_code": code,
            "model_id": m["model_id"],
            "device_type": m.get("device_type"),
            "part_description": m.get("part_description"),
            "display_name": m.get("mobile_display_name_key"),
            "firmware_type": m.get("firmware_type"),
        })
    return out


def main() -> int:
    print(f"fetching {CATALOG_URL}")
    raw = fetch_catalog()
    print(f"  {len(raw)} raw entries")

    models = collapse(raw)
    print(f"  {len(models)} unique published model_codes")

    MODELS_PATH.write_text(json.dumps(models, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {MODELS_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
