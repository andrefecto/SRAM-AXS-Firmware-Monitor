# Contributing

## Add or adjust a curated group

Curated groups let subscribers pull a bundle of related model feeds with one URL (e.g. "all Rival AXS components"). They live in [`groups.json`](groups.json). Each entry looks like:

```json
{
  "id": "force-axs-road",
  "title": "SRAM Force AXS (road)",
  "description": "All generations of Force AXS road groupsets — derailleurs, shifters, Force power meter.",
  "models": ["RD-FRC-E-D2", "FD-FRC-E-D2", "ED-FRC-D2", "..."]
}
```

- `id` must be lowercase-kebab-case. It becomes the URL slug (`feeds/group/{id}.atom`).
- Every `model_code` listed must exist in [`models.json`](models.json). Check `jq -r '.[].model_code' models.json` for the canonical list.
- A model can appear in multiple groups. Use groups that match how riders actually shop — not internal SRAM taxonomy.

### Testing a group change locally

```bash
python3 scripts/generate_feeds.py   # regenerates docs/feeds/ from current state/
```

Open `docs/feeds/group/<your-id>.atom` in a text editor or a browser — valid Atom XML confirms the group is wired up.

## Report a broken feed or missing model

Open an issue with:

- The affected `model_code` (or the group ID).
- What you expected vs. what you see.
- If it's a feed URL that 404s, paste the URL.

## Report a SRAM API schema change

If the daily workflow exits non-zero with an "anomaly" for a model, the SRAM firmware-service API has probably changed shape. Attach the anomaly text from the workflow log to an issue — the fix usually lives in `scripts/check_firmware.py` under `pick_newest_prod` / `extract_ts`.

## Out of scope (for now)

- **Beta firmware feeds.** The script filters on `beta == 0`. Beta-channel feeds are a stretch goal; PR welcome.
- **Localised release notes.** SRAM's API returns English-only notes; we pass them through as-is.
- **Historical firmware archives / binaries.** This repo stores release metadata only.
