#!/usr/bin/env python3
"""Pull NJDOT crash data for a county, filter to a municipality, map to the
Hopewell crash-map schema, and emit a CSV.

NJDOT publishes per-county fixed-field annual files at:
  https://www.state.nj.us/transportation/refdata/accident/<YEAR>/<County><YEAR>Accidents.zip
Format: one crash per line, comma-separated, fields in the order given by
CrashTable.pdf. Latitude/Longitude are frequently blank (and occasionally
wrong), so --geocode is offered to fill them from the intersection text.

Usage:
  python3 pull_njdot.py --county Mercer --municipality "HOPEWELL BORO" \
      --years 2021 2022 --out njdot_hopewell.csv [--geocode]
"""
import argparse, csv, io, sys, time, urllib.parse, urllib.request, zipfile

BASE = "https://www.state.nj.us/transportation/refdata/accident"
UA = "hopewell-crash-map/1.0"

# 0-based comma-field indices (validated against CrashTable.pdf + real records)
I_KEY, I_MUNI, I_DATE, I_TIME = 0, 2, 3, 5
I_KILLED, I_INJURED, I_PEDK, I_PEDI = 9, 10, 11, 12
I_SEVERITY, I_CRASHTYPE = 13, 17
I_LOCATION, I_CROSS_A, I_CROSS_B = 19, 36, 38
I_LAT, I_LNG = 45, 46

SEVERITY = {"F": "fatal", "I": "injury", "P": "property_damage"}


def fetch_year(county, year):
    url = f"{BASE}/{year}/{county}{year}Accidents.zip"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        raw = urllib.request.urlopen(req, timeout=60).read()
    except Exception as e:
        print(f"  {year}: FETCH FAILED ({e}) — skipping", file=sys.stderr)
        return []
    zf = zipfile.ZipFile(io.BytesIO(raw))
    name = zf.namelist()[0]
    return zf.read(name).decode("latin-1").splitlines()


def crash_type(p):
    # Only pedestrian involvement is unambiguously flagged in this table.
    if (int(p[I_PEDK] or 0) + int(p[I_PEDI] or 0)) > 0:
        return "pedestrian"
    return "vehicle"  # bicycle is NOT reliably distinguishable from this table


def coords(p):
    la, lo = p[I_LAT].strip(), p[I_LNG].strip()
    if not (la and lo):
        return "", ""
    try:
        laf, lof = float(la), -abs(float(lo))
        # sanity box: New Jersey only
        if 38.5 <= laf <= 41.5 and -75.6 <= lof <= -73.8:
            return f"{laf:.6f}", f"{lof:.6f}"
    except ValueError:
        pass
    return "", ""


def geocode(location, cross, cache):
    """Best-effort intersection geocode via OSM Nominatim. Approximate."""
    key = (location, cross)
    if key in cache:
        return cache[key]
    q = f"{location} and {cross}, Hopewell, New Jersey, USA"
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
        {"format": "json", "limit": 1, "q": q})
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        import json
        d = json.loads(urllib.request.urlopen(req, timeout=30).read())
        res = (f"{float(d[0]['lat']):.6f}", f"{float(d[0]['lon']):.6f}") if d else ("", "")
    except Exception:
        res = ("", "")
    cache[key] = res
    time.sleep(1.1)  # Nominatim rate limit
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--county", default="Mercer")
    ap.add_argument("--municipality", default="HOPEWELL BORO", help="as it appears in the data")
    ap.add_argument("--years", nargs="+", type=int, required=True)
    ap.add_argument("--out", default="njdot_hopewell.csv")
    ap.add_argument("--geocode", action="store_true",
                    help="fill missing coords from the intersection text (approximate)")
    args = ap.parse_args()

    rows, gc_cache = [], {}
    for year in args.years:
        lines = fetch_year(args.county, year)
        hits = 0
        for line in lines:
            p = [c.strip() for c in line.split(",")]
            if len(p) <= I_LNG or p[I_MUNI] != args.municipality:
                continue
            hits += 1
            case = p[I_KEY][8:].strip()          # drop year+county+muni prefix
            mm, dd, yy = p[I_DATE].split("/")
            date = f"{yy}-{mm}-{dd}"
            t = p[I_TIME].zfill(4)
            time_s = f"{t[:2]}:{t[2:]}" if t.strip("0") else ""
            cross = (p[I_CROSS_B] or p[I_CROSS_A]).strip()
            location = p[I_LOCATION].strip()
            loc_label = f"{location} & {cross}" if cross and cross not in ("AT",) else location
            lat, lng = coords(p)
            if not (lat and lng) and args.geocode and location:
                lat, lng = geocode(location, cross, gc_cache)
            rows.append({
                "id": case, "date": date, "time": time_s,
                "municipality": "Hopewell Borough", "location": loc_label,
                "lat": lat, "lng": lng, "crash_type": crash_type(p),
                "severity": SEVERITY.get(p[I_SEVERITY], "other"),
                "description": "", "source_url": "",
            })
        print(f"  {year}: {hits} {args.municipality} crashes", file=sys.stderr)

    hdr = ["id","date","time","municipality","location","lat","lng",
           "crash_type","severity","description","source_url"]
    with open(args.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=hdr)
        w.writeheader(); w.writerows(rows)

    n_coord = sum(1 for r in rows if r["lat"] and r["lng"])
    print(f"\nWrote {len(rows)} rows -> {args.out}  ({n_coord} with coordinates)", file=sys.stderr)


if __name__ == "__main__":
    main()
