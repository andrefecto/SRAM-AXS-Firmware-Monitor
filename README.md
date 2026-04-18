# SRAM AXS Firmware Monitor

Unofficial RSS/Atom feeds that notify you when SRAM releases new production firmware for your AXS components. Subscribe only to what you own — a road rider doesn't need pings about XX Transmission drops.

**Subscribe here: https://andrefecto.github.io/SRAM-AXS-Firmware-Monitor/**

There's no signup, account, or email list. You pick the feed URLs that match your gear, paste them into your RSS reader (Feedly, Inoreader, NetNewsWire, Miniflux, Thunderbird, etc.), and that's it.

## What's tracked

Every model that SRAM lists in their public firmware catalog at `nexus.quarqnet.com/api/v2/models/` — about 85 unique components today. The list is refreshed monthly; new models auto-join within a day of the next catalog refresh.

Only **production** firmware is tracked. Beta releases are excluded.

## Feed types

| Scope | URL | When to use |
|---|---|---|
| Firehose | `feeds/all.atom` | You want to see everything. |
| Curated group | `feeds/group/{group_id}.atom` | You want a bundle (e.g. "all Force AXS road components"). |
| Single model | `feeds/{MODEL_CODE}.atom` | You only care about one specific component. |

See the [subscription directory](https://andrefecto.github.io/SRAM-AXS-Firmware-Monitor/) for every URL.

## Alternative: GitHub Releases

Each batch of firmware updates also cuts a GitHub Release. If you prefer GitHub notifications over an RSS reader:

- Click **Watch → Custom → Releases** on this repo, or
- Subscribe to `https://github.com/andrefecto/SRAM-AXS-Firmware-Monitor/releases.atom`.

## How it works

A GitHub Actions workflow runs daily at 14:00 UTC:

1. Polls `https://api.axs.sram.com/firmware-service/v2/firmware/{model_id}` for every model in [`models.json`](models.json).
2. Diffs the newest non-beta release against [`state/{MODEL_CODE}.json`](state/).
3. On any change, prepends to that model's history, regenerates the per-model / group / all-updates Atom feeds in [`docs/feeds/`](docs/feeds/), and commits everything back to `main`.
4. Cuts a GitHub Release summarising the batch.

Silent success means no commit, no release. Runs cost $0 — public repos get unlimited GitHub Actions minutes.

If the SRAM API changes shape, the workflow exits non-zero and GitHub emails the repo owner. Please [open an issue](https://github.com/andrefecto/SRAM-AXS-Firmware-Monitor/issues) if you notice feeds have gone stale for a model you're watching.

## Contributing

- **Want a new curated group?** Edit [`groups.json`](groups.json) and PR — see [CONTRIBUTING.md](CONTRIBUTING.md).
- **Model missing or feed stale?** File an issue with the `model_code`.

## Disclaimer

Not affiliated with, endorsed by, or sponsored by SRAM. This project polls SRAM's public firmware-service API and republishes the release metadata as RSS. All firmware belongs to SRAM; this repo stores no firmware binaries.
