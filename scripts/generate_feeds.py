#!/usr/bin/env python3
"""Generate Atom feeds + subscription-directory index from state/*.json.

Outputs:
  docs/feeds/{MODEL_CODE}.atom     — per-model feed, one <entry> per history item.
  docs/feeds/group/{group_id}.atom — group feed (union of member models, newest first).
  docs/feeds/all.atom              — firehose feed across every model.
  docs/index.html                  — subscription directory, grouped by family.

Feed IDs use the public Pages URL so RSS readers dedupe correctly across
renderings. Feeds are valid Atom 1.0; no external dependencies beyond the
Python stdlib.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import os
from pathlib import Path
from xml.sax.saxutils import escape

REPO_ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = REPO_ROOT / "state"
FEEDS_DIR = REPO_ROOT / "docs" / "feeds"
GROUP_DIR = FEEDS_DIR / "group"
INDEX_PATH = REPO_ROOT / "docs" / "index.html"
GROUPS_PATH = REPO_ROOT / "groups.json"

SITE_BASE = os.environ.get(
    "SITE_BASE",
    "https://andrefecto.github.io/SRAM-AXS-Firmware-Monitor",
)
REPO_URL = "https://github.com/andrefecto/SRAM-AXS-Firmware-Monitor"

ALL_FEED_CAP = 200
GROUP_FEED_CAP = 100


def iso(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_state() -> list[dict]:
    docs = []
    for p in sorted(STATE_DIR.glob("*.json")):
        docs.append(json.loads(p.read_text(encoding="utf-8")))
    return docs


def atom_entry(state: dict, h: dict) -> str:
    code = state["model_code"]
    version = h["version"]
    name = state.get("display_name") or code
    part = state.get("part_description") or ""
    entry_id = f"{SITE_BASE}/feeds/{code}.atom#{version}"
    notes = h.get("release_notes") or ""
    body = (
        f"<p><strong>{escape(name)}</strong> "
        f"<code>{escape(code)}</code> — firmware {escape(version)}</p>"
    )
    if part:
        body += f"<p>Part: {escape(part)}</p>"
    if notes:
        body += f"<p>{escape(notes)}</p>"
    body += (
        f"<p>Released: {escape(h['release_date'])}</p>"
    )
    link = h.get("link") or f"{SITE_BASE}/feeds/{code}.atom"
    return (
        "  <entry>\n"
        f"    <title>{escape(name)} ({escape(code)}) — firmware {escape(version)}</title>\n"
        f"    <id>{escape(entry_id)}</id>\n"
        f"    <updated>{iso(h['release_ts'])}</updated>\n"
        f"    <published>{iso(h['release_ts'])}</published>\n"
        f"    <link rel=\"alternate\" href=\"{escape(link)}\"/>\n"
        "    <author><name>SRAM AXS Firmware Monitor</name></author>\n"
        f"    <summary type=\"html\">{escape(body)}</summary>\n"
        "  </entry>\n"
    )


def atom_feed(title: str, self_url: str, subtitle: str, entries_xml: str, latest_ts: float | None) -> str:
    updated = iso(latest_ts) if latest_ts else iso(dt.datetime.now(dt.timezone.utc).timestamp())
    feed_id = self_url
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<feed xmlns="http://www.w3.org/2005/Atom">\n'
        f"  <title>{escape(title)}</title>\n"
        f"  <subtitle>{escape(subtitle)}</subtitle>\n"
        f"  <id>{escape(feed_id)}</id>\n"
        f"  <link rel=\"self\" href=\"{escape(self_url)}\"/>\n"
        f"  <link rel=\"alternate\" href=\"{escape(REPO_URL)}\"/>\n"
        f"  <updated>{updated}</updated>\n"
        "  <generator uri=\"https://github.com/andrefecto/SRAM-AXS-Firmware-Monitor\">SRAM AXS Firmware Monitor</generator>\n"
        f"{entries_xml}"
        "</feed>\n"
    )


def write_model_feed(state: dict) -> None:
    code = state["model_code"]
    history = state.get("history", [])
    if not history:
        return
    entries_xml = "".join(atom_entry(state, h) for h in history)
    latest_ts = history[0]["release_ts"]
    name = state.get("display_name") or code
    feed = atom_feed(
        title=f"{name} ({code}) — firmware",
        self_url=f"{SITE_BASE}/feeds/{code}.atom",
        subtitle=f"Production firmware releases for SRAM {code}.",
        entries_xml=entries_xml,
        latest_ts=latest_ts,
    )
    (FEEDS_DIR / f"{code}.atom").write_text(feed, encoding="utf-8")


def collect_entries(states: list[dict]) -> list[tuple[dict, dict]]:
    """Flatten (state, history_item) pairs, newest first."""
    pairs: list[tuple[dict, dict]] = []
    for s in states:
        for h in s.get("history", []):
            pairs.append((s, h))
    pairs.sort(key=lambda p: p[1]["release_ts"], reverse=True)
    return pairs


def write_group_feed(group: dict, states_by_code: dict[str, dict]) -> bool:
    members = [states_by_code[c] for c in group["models"] if c in states_by_code]
    pairs = collect_entries(members)[:GROUP_FEED_CAP]
    if not pairs:
        return False
    entries_xml = "".join(atom_entry(s, h) for s, h in pairs)
    latest_ts = pairs[0][1]["release_ts"]
    feed = atom_feed(
        title=group["title"],
        self_url=f"{SITE_BASE}/feeds/group/{group['id']}.atom",
        subtitle=group["description"],
        entries_xml=entries_xml,
        latest_ts=latest_ts,
    )
    (GROUP_DIR / f"{group['id']}.atom").write_text(feed, encoding="utf-8")
    return True


def write_all_feed(states: list[dict]) -> None:
    pairs = collect_entries(states)[:ALL_FEED_CAP]
    if not pairs:
        return
    entries_xml = "".join(atom_entry(s, h) for s, h in pairs)
    latest_ts = pairs[0][1]["release_ts"]
    feed = atom_feed(
        title="SRAM AXS Firmware — all updates",
        self_url=f"{SITE_BASE}/feeds/all.atom",
        subtitle="Every production firmware release across every tracked SRAM AXS model.",
        entries_xml=entries_xml,
        latest_ts=latest_ts,
    )
    (FEEDS_DIR / "all.atom").write_text(feed, encoding="utf-8")


def render_index(states: list[dict], groups: list[dict]) -> str:
    states_by_code = {s["model_code"]: s for s in states}
    # "Latest firmware activity" — pulled from the newest release_ts we've
    # observed across all tracked models. Stable across reruns (only moves
    # when a new firmware is actually detected), so regenerating this page
    # produces a no-op diff unless state changed.
    latest_ts = max(
        (h["release_ts"] for s in states for h in s.get("history", [])),
        default=None,
    )
    latest_label = (
        dt.datetime.fromtimestamp(latest_ts, tz=dt.timezone.utc).strftime("%Y-%m-%d")
        if latest_ts else "—"
    )
    rows_all = [
        f'<li><a href="feeds/all.atom">feeds/all.atom</a> — firehose, every tracked model</li>'
    ]
    group_items = []
    for g in groups:
        if not any(c in states_by_code for c in g["models"]):
            continue
        member_list = ", ".join(
            f'<code>{html.escape(c)}</code>' for c in g["models"] if c in states_by_code
        )
        group_items.append(
            f'<li><a href="feeds/group/{html.escape(g["id"])}.atom">feeds/group/{html.escape(g["id"])}.atom</a> — '
            f'<strong>{html.escape(g["title"])}</strong>. {html.escape(g["description"])}<br>'
            f'<small>{member_list}</small></li>'
        )
    per_model_items = []
    for s in states:
        code = s["model_code"]
        name = s.get("display_name") or code
        part = s.get("part_description") or ""
        current = s["history"][0]["version"] if s.get("history") else "—"
        per_model_items.append(
            f'<tr><td><a href="feeds/{html.escape(code)}.atom"><code>{html.escape(code)}</code></a></td>'
            f'<td>{html.escape(name)}</td>'
            f'<td>{html.escape(part)}</td>'
            f'<td>{html.escape(current)}</td></tr>'
        )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>SRAM AXS Firmware Monitor — RSS feeds</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  body {{ font-family: -apple-system, Segoe UI, sans-serif; max-width: 860px; margin: 2rem auto; padding: 0 1rem; color: #222; }}
  h1 {{ margin-bottom: 0.2rem; }}
  h2 {{ margin-top: 2.2rem; border-bottom: 1px solid #ddd; padding-bottom: 0.3rem; }}
  code {{ background: #f3f3f3; padding: 0 4px; border-radius: 3px; font-size: 0.95em; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 0.92em; }}
  th, td {{ border-bottom: 1px solid #eee; padding: 4px 8px; text-align: left; }}
  th {{ background: #fafafa; }}
  ul.groups li {{ margin-bottom: 0.6rem; }}
  .muted {{ color: #666; }}
  footer {{ margin-top: 3rem; font-size: 0.9em; color: #666; border-top: 1px solid #ddd; padding-top: 1rem; }}
</style>
</head>
<body>
<h1>SRAM AXS Firmware Monitor</h1>
<p class="muted">Unofficial RSS feeds for SRAM AXS component firmware releases. Subscribe only to the feeds that match your gear.</p>
<p class="muted">Most recent firmware activity: {latest_label}. Source: <a href="{REPO_URL}">{REPO_URL}</a>.</p>

<h2>How to subscribe</h2>
<p>Copy any <code>.atom</code> URL below into your RSS reader (Feedly, Inoreader, NetNewsWire, Miniflux, Thunderbird, etc.). You will only get notified when a new production firmware is released for a model in that feed. Beta firmware is excluded.</p>
<p>Prefer GitHub notifications? <a href="{REPO_URL}/releases.atom">Watch releases</a> — one release is cut per update batch.</p>

<h2>Firehose</h2>
<ul>{''.join(rows_all)}</ul>

<h2>Curated groups</h2>
<ul class="groups">{''.join(group_items)}</ul>

<h2>Per-model feeds</h2>
<p class="muted">Every tracked model has its own feed. Pick exactly what you own.</p>
<table>
<thead><tr><th>Model code</th><th>Display name</th><th>Part</th><th>Current</th></tr></thead>
<tbody>{''.join(per_model_items)}</tbody>
</table>

<footer>
<p>Not affiliated with SRAM. Data pulled from SRAM's public firmware-service API.
A missing firmware release here means the monitor has not yet polled — give it up to 24 hours.
Found a bug or want to propose a new curated group? <a href="{REPO_URL}/issues">Open an issue</a> or a PR against <code>groups.json</code>.</p>
</footer>
</body>
</html>
"""


def main() -> int:
    FEEDS_DIR.mkdir(parents=True, exist_ok=True)
    GROUP_DIR.mkdir(parents=True, exist_ok=True)

    states = load_state()
    if not states:
        print("state/ is empty — nothing to generate")
        return 0

    for s in states:
        write_model_feed(s)
    print(f"wrote {len(states)} per-model feeds")

    write_all_feed(states)
    print("wrote feeds/all.atom")

    groups = json.loads(GROUPS_PATH.read_text(encoding="utf-8"))
    states_by_code = {s["model_code"]: s for s in states}
    written = sum(1 for g in groups if write_group_feed(g, states_by_code))
    print(f"wrote {written}/{len(groups)} group feeds")

    INDEX_PATH.write_text(render_index(states, groups), encoding="utf-8")
    print(f"wrote {INDEX_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
