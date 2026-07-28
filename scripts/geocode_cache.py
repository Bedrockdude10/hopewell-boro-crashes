#!/usr/bin/env python3
"""Geocode the unique Hopewell intersections from NJDOT crash records, robustly.
Rotates Overpass endpoints, retries with backoff, caches to geocode_cache.json.

Reads every "*Accidents.txt" in the working directory (or --datadir).
"""
import argparse, glob, json, os, re, sys, time, urllib.parse, urllib.request

UA = "hopewell-crash-map/1.0"
ENDPOINTS = ["https://overpass-api.de/api/interpreter",
             "https://overpass.kumi.systems/api/interpreter",
             "https://overpass.private.coffee/api/interpreter"]
ABBR = {" AVE": " Avenue", " ST": " Street", " RD": " Road", " PL": " Place",
        " DR": " Drive", " LN": " Lane", " CT": " Court"}


def titlecase(s):
    s = re.sub(r"\*+", "", s)
    s = re.sub(r"\s+", " ", s.strip()).title()
    for k, v in ABBR.items():
        if s.upper().endswith(k):
            s = s[:len(s) - len(k)] + v
    return s


def road_names(raw):
    raw = raw.strip()
    if raw.startswith("ROUTE 518") or "BROAD" in raw:
        return ["Broad Street"]
    if "COLUMBIA" in raw and "GREENWOOD" in raw:
        return ["Greenwood Avenue", "Columbia Avenue"]
    if raw.startswith("MERCER COUNTY 654"):
        return ["Greenwood Avenue", "Hopewell Princeton Road", "Louellen Street"]
    if raw.startswith("SEMINARY"):
        return ["Seminary Avenue"]
    return [titlecase(raw.split("/")[0])]


def cross_names(raw):
    raw = re.sub(r"ROUTE \d+ / ", "", raw.strip())
    raw = re.sub(r"ROUTE 518.*", "Broad Street", raw)
    raw = raw.split(" / ")[0].strip()
    return [titlecase(raw)] if raw else []


def query(a, b, municipality):
    q = (f'[out:json][timeout:25];area[name="{municipality}"][admin_level=8]->.a;'
         f'way(area.a)[highway][name~"{a}"]->.wa;way(area.a)[highway][name~"{b}"]->.wb;'
         f'node(w.wa)(w.wb);out;')
    for attempt in range(6):
        ep = ENDPOINTS[attempt % len(ENDPOINTS)]
        try:
            data = urllib.request.urlopen(urllib.request.Request(
                ep, data=urllib.parse.urlencode({"data": q}).encode(),
                headers={"User-Agent": UA}), timeout=40).read()
            els = json.loads(data).get("elements", [])
            return [round(els[0]["lat"], 6), round(els[0]["lon"], 6)] if els else None
        except Exception as e:
            print(f"    [{ep.split('/')[2]}] {str(e)[:50]} (retry in {2**attempt}s)", file=sys.stderr)
            time.sleep(2 ** attempt)
    return None


def g(p, i):
    return p[i].strip() if i < len(p) else ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--datadir", default=".")
    ap.add_argument("--municipality-name", default="HOPEWELL BORO", help="value in the data file")
    ap.add_argument("--osm-area", default="Hopewell", help="OSM admin_level=8 area name")
    ap.add_argument("--cache", default="geocode_cache.json")
    args = ap.parse_args()

    cache = json.load(open(args.cache)) if os.path.exists(args.cache) else {}
    files = sorted(glob.glob(os.path.join(args.datadir, "*Accidents.txt")))
    if not files:
        sys.exit(f"No *Accidents.txt found in {args.datadir}")
    pairs = {}
    for path in files:
        for line in open(path, encoding="latin-1"):
            p = [c.strip() for c in line.split(",")]
            if len(p) < 47 or p[2] != args.municipality_name:
                continue
            loc, cross = g(p, 19), g(p, 38)
            if not cross:
                continue
            for a in road_names(loc):
                for b in cross_names(cross):
                    pairs.setdefault(f"{a}|{b}", (a, b))
    print(f"{len(pairs)} unique intersection candidates", file=sys.stderr)
    for key, (a, b) in pairs.items():
        if key in cache:
            print(f"  cached  {key} -> {cache[key]}", file=sys.stderr); continue
        res = query(a, b, args.osm_area)
        cache[key] = res
        json.dump(cache, open(args.cache, "w"), indent=0)
        print(f"  {'OK  ' if res else 'MISS'}  {key} -> {res}", file=sys.stderr)
        time.sleep(1.5)
    resolved = sum(1 for v in cache.values() if v)
    print(f"\nDONE: {resolved}/{len(cache)} resolved -> {args.cache}", file=sys.stderr)


if __name__ == "__main__":
    main()
