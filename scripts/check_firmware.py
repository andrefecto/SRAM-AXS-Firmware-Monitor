#!/usr/bin/env python3
"""Poll SRAM firmware API, diff against state/*.json, write updated state.

For every model in models.json, fetch
  https://api.axs.sram.com/firmware-service/v2/firmware/{model_id}
pick the newest non-beta release (by release_date, falling back to
upload_ts), and compare to the current state file. On a change, prepend
to the per-model history (capped) and record the change in a summary.

Writes the change summary to $CHANGES_JSON (default /tmp/firmware-changes.json)
so the workflow and generate_feeds.py can consume it.

Exits non-zero on any schema anomaly so GitHub's default workflow-failure
email reaches the repo owner.

Usage:
  python3 scripts/check_firmware.py            # normal run — writes state/
  python3 scripts/check_firmware.py --dry-run  # writes state_tmp/, leaves state/ untouched
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

FIRMWARE_URL = "https://api.axs.sram.com/firmware-service/v2/firmware/{model_id}"
REPO_ROOT = Path(__file__).resolve().parent.parent
MODELS_PATH = REPO_ROOT / "models.json"
STATE_DIR = REPO_ROOT / "state"
STATE_DIR_DRY = REPO_ROOT / "state_tmp"
HISTORY_CAP = 50
SEED_HISTORY = 10
REQUEST_TIMEOUT = 30
INTER_REQUEST_SLEEP = 0.05

UA = "SRAM-AXS-Firmware-Monitor (+https://github.com/andrefecto/SRAM-AXS-Firmware-Monitor)"


class Anomaly(RuntimeError):
    pass


def fetch_firmware(model_id: int) -> list[dict]:
    url = FIRMWARE_URL.format(model_id=model_id)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as e:
        raise Anomaly(f"HTTP {e.code} from {url}") from e
    except urllib.error.URLError as e:
        raise Anomaly(f"network error for {url}: {e.reason}") from e
    if not isinstance(data, list):
        raise Anomaly(f"{url} returned {type(data).__name__}, expected list")
    return data


def extract_ts(entry: dict) -> float | None:
    for key in ("release_date", "upload_ts"):
        v = entry.get(key)
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
    return None


def pick_newest_prod(entries: list[dict], model_code: str) -> dict | None:
    """Return the newest non-beta entry, with a normalized `ts` float field."""
    valid = []
    for e in entries:
        if "version" not in e or "beta" not in e:
            raise Anomaly(
                f"{model_code}: firmware entry missing required field "
                f"(version/beta): keys={sorted(e.keys())}"
            )
        ts = extract_ts(e)
        if ts is None:
            raise Anomaly(
                f"{model_code}: firmware entry {e.get('version')!r} has "
                f"neither release_date nor upload_ts"
            )
        if e.get("beta") == 0:
            enriched = dict(e)
            enriched["ts"] = ts
            valid.append(enriched)
    if not valid:
        return None
    valid.sort(key=lambda e: e["ts"], reverse=True)
    return valid[0]


def fmt_date(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc).strftime("%Y-%m-%d")


def history_entry(fw: dict) -> dict:
    notes = fw.get("release_notes") or ""
    return {
        "version": str(fw["version"]),
        "release_date": fmt_date(fw["ts"]),
        "release_ts": fw["ts"],
        "release_notes": notes.strip(),
        "link": fw.get("link"),
    }


def load_state(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_state(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


def process_model(model: dict, out_dir: Path) -> dict | None:
    """Return a change dict if firmware advanced, else None.

    Raises Anomaly on schema issues, caught by the caller so one broken
    model can fail the whole run.
    """
    code = model["model_code"]
    model_id = model["model_id"]
    path = out_dir / f"{code}.json"

    raw = fetch_firmware(model_id)
    newest = pick_newest_prod(raw, code)
    if newest is None:
        # No production firmware ever — skip silently (rare: unreleased product).
        return None

    new_entry = history_entry(newest)
    existing = load_state(path)

    if existing is None:
        # Seed: take top N non-beta entries as history backfill.
        seed_entries = []
        for e in raw:
            if e.get("beta") != 0:
                continue
            ts = extract_ts(e)
            if ts is None:
                continue
            enriched = dict(e)
            enriched["ts"] = ts
            seed_entries.append(history_entry(enriched))
        seed_entries.sort(key=lambda h: h["release_ts"], reverse=True)
        doc = {
            "model_code": code,
            "model_id": model_id,
            "display_name": model.get("display_name"),
            "part_description": model.get("part_description"),
            "history": seed_entries[:SEED_HISTORY],
        }
        write_state(path, doc)
        return None  # seed does not count as an update

    current = existing["history"][0] if existing.get("history") else None
    if current and current["version"] == new_entry["version"]:
        # unchanged — also keep metadata fresh in case catalog renamed something
        if (
            existing.get("display_name") != model.get("display_name")
            or existing.get("part_description") != model.get("part_description")
        ):
            existing["display_name"] = model.get("display_name")
            existing["part_description"] = model.get("part_description")
            write_state(path, existing)
        return None

    # Firmware advanced: prepend + cap.
    history = [new_entry] + existing.get("history", [])
    history = history[:HISTORY_CAP]
    doc = {
        "model_code": code,
        "model_id": model_id,
        "display_name": model.get("display_name"),
        "part_description": model.get("part_description"),
        "history": history,
    }
    write_state(path, doc)

    return {
        "model_code": code,
        "model_id": model_id,
        "display_name": model.get("display_name"),
        "part_description": model.get("part_description"),
        "from_version": current["version"] if current else None,
        "to_version": new_entry["version"],
        "release_date": new_entry["release_date"],
        "release_notes": new_entry["release_notes"],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="Write state to state_tmp/ instead of state/")
    args = ap.parse_args()

    out_dir = STATE_DIR_DRY if args.dry_run else STATE_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    models = json.loads(MODELS_PATH.read_text(encoding="utf-8"))
    print(f"checking {len(models)} models → {out_dir.relative_to(REPO_ROOT)}/")

    # A run is a "seed" when no per-model state files exist yet in out_dir.
    is_seed = not any(out_dir.glob("*.json"))

    changes: list[dict] = []
    anomalies: list[str] = []
    for i, m in enumerate(models, 1):
        try:
            change = process_model(m, out_dir)
        except Anomaly as e:
            anomalies.append(str(e))
            print(f"  [{i}/{len(models)}] {m['model_code']}: ANOMALY {e}", flush=True)
            continue
        if change:
            changes.append(change)
            print(f"  [{i}/{len(models)}] {m['model_code']}: "
                  f"{change['from_version']} → {change['to_version']}", flush=True)
        time.sleep(INTER_REQUEST_SLEEP)

    summary = {
        "generated_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "seed_run": is_seed,
        "total_models": len(models),
        "changes": changes,
        "anomalies": anomalies,
    }

    changes_path = Path(os.environ.get("CHANGES_JSON", "/tmp/firmware-changes.json"))
    changes_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {changes_path}")

    print(
        f"summary: seed={is_seed} changes={len(changes)} "
        f"anomalies={len(anomalies)}"
    )

    if anomalies:
        # Fail the run so GitHub emails the owner.
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
