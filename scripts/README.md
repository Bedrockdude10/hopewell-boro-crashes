# Crash-data scripts

Helper scripts for maintaining the crash map's data. The map reads from a
published Google Sheet (see the root `README.md`); these scripts add rows to that
Sheet and pull crashes from NJDOT's public data. **All data changes go to the
Sheet — the site picks them up on next load, no redeploy.**

## Setup

```bash
pip install -r scripts/requirements.txt   # gspread, google-auth
```

Writing to the Sheet needs a Google **service-account key** (JSON) whose email has
**Editor** access to the Sheet. Keep the key **outside version control** — the repo
is public and `.gitignore` already excludes `hopewell-boro-crashes-*.json`.

## 1. Add rows to the Sheet — `append_crashes.py`

Idempotent (de-dupes on `id`, so re-runs never duplicate). Always `--dry-run` first.

```bash
python3 scripts/append_crashes.py \
  --key   /path/to/service-account.json \
  --sheet "https://docs.google.com/spreadsheets/d/<ID>/edit" \
  --csv   new_rows.csv \
  --dry-run          # preview; drop this flag to actually write
```

CSV must have the 11-column header: `id,date,time,municipality,location,lat,lng,crash_type,severity,description,source_url`.

## 2. Pull NJDOT crashes for a municipality — `pull_njdot.py`

Downloads NJDOT's per-county annual file, filters to a municipality, maps to the
schema. NJDOT lags ~3 years (latest ≈ 2022) and its lat/lng are mostly blank/wrong,
so use the geocoding step below for map-ready coordinates.

```bash
mkdir -p scripts/data && cd scripts/data
python3 ../pull_njdot.py --county Mercer --municipality "HOPEWELL BORO" \
  --years 2021 2022 --out njdot_hopewell.csv
```

## 3. Geocode + describe (map-ready rows) — `geocode_cache.py` + `build_njdot_rows.py`

`pull_njdot.py` also downloads the raw `*Accidents.txt` files into the working dir.
From that dir:

```bash
# a) geocode the unique intersections (Overpass; cached, safe to re-run)
python3 ../geocode_cache.py --osm-area Hopewell --municipality-name "HOPEWELL BORO"

# b) build rows: classify NJTR-1 type, place at intersection + offset, write descriptions
python3 ../build_njdot_rows.py --municipality-name "HOPEWELL BORO" \
  --municipality-label "Hopewell Borough" --out njdot_hopewell.csv

# c) review, then append (step 1)
python3 ../append_crashes.py --key <key> --sheet <url> --csv njdot_hopewell.csv --dry-run
```

`manual_overrides.json` (optional, `{ "CASE_ID": [lat, lng] }`) places records that
can't be geocoded to an intersection (addresses, edge-of-town streets).

## Notes / gotchas

- **Placement is intersection-level (approximate)** — NJDOT gives no usable coordinates.
- **Crash type comes from the NJTR-1 code**, not the pedestrian-count fields:
  `13 = pedestrian`, `14 = bicyclist`. (Those count fields can be 0 for a fatal cyclist.)
- Field parsing is by **comma-field order**, not character position (text fields
  aren't padded to the spec in `CrashTable.pdf`).
- `scripts/data/` is gitignored (downloaded zips/txt + generated CSVs/caches).
