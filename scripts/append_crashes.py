#!/usr/bin/env python3
"""Append new crash rows to the Hopewell crash-map Google Sheet.

Idempotent: skips any row whose `id` already exists in the sheet, so re-running
can never create duplicates. Use --dry-run to preview without writing.

Usage:
  python3 append_crashes.py \
      --key   /path/to/service-account.json \
      --sheet "<editable Google Sheet URL or spreadsheet id>" \
      --csv   new_crashes.csv \
      [--worksheet "Sheet1"] [--dry-run]
"""
import argparse, csv, sys
import gspread
from google.oauth2.service_account import Credentials

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
HEADERS = ["id","date","time","municipality","location","lat","lng",
           "crash_type","severity","description","source_url"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", required=True, help="Service account JSON key path")
    ap.add_argument("--sheet", required=True, help="Sheet URL or spreadsheet id")
    ap.add_argument("--csv", required=True, help="CSV of new rows (with header)")
    ap.add_argument("--worksheet", default=None, help="Tab name (default: first tab)")
    ap.add_argument("--dry-run", action="store_true", help="Preview only, no write")
    args = ap.parse_args()

    creds = Credentials.from_service_account_file(args.key, scopes=SCOPES)
    gc = gspread.authorize(creds)

    sh = (gc.open_by_url(args.sheet) if args.sheet.startswith("http")
          else gc.open_by_key(args.sheet))
    ws = sh.worksheet(args.worksheet) if args.worksheet else sh.sheet1

    existing = ws.get_all_values()
    if not existing:
        print("Sheet is empty — refusing to run. Add the header row first.", file=sys.stderr)
        sys.exit(1)
    header = [h.strip() for h in existing[0]]
    if header[:len(HEADERS)] != HEADERS:
        print(f"WARNING: sheet header does not match expected schema.\n"
              f"  sheet:    {header}\n  expected: {HEADERS}", file=sys.stderr)
    id_col = header.index("id")
    existing_ids = {r[id_col].strip() for r in existing[1:] if len(r) > id_col and r[id_col].strip()}

    with open(args.csv, newline="") as f:
        rows = list(csv.DictReader(f))

    to_add, skipped = [], []
    for r in rows:
        (skipped if r["id"].strip() in existing_ids else to_add).append(r)

    print(f"Existing rows in sheet: {len(existing)-1}")
    print(f"CSV rows: {len(rows)}  |  new: {len(to_add)}  |  already present (skipped): {len(skipped)}")
    for r in skipped:
        print(f"  skip  {r['id']}  ({r['location']})")
    for r in to_add:
        print(f"  ADD   {r['id']}  {r['date']}  {r['location']}  [{r['crash_type']}/{r['severity']}]")

    if not to_add:
        print("Nothing new to add.")
        return
    if args.dry_run:
        print("\n--dry-run: no changes written.")
        return

    values = [[r.get(h, "") for h in header] for r in to_add]
    ws.append_rows(values, value_input_option="USER_ENTERED")
    print(f"\nAppended {len(values)} row(s) to '{ws.title}'.")


if __name__ == "__main__":
    main()
