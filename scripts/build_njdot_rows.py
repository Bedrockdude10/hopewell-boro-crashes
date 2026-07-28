#!/usr/bin/env python3
"""Build map-ready rows from NJDOT crash records for one municipality.

Classifies crash type from the NJTR-1 code, geocodes the exact intersection
(via geocode_cache.json, produced by geocode_cache.py), offsets by the recorded
distance+direction from the cross street, and writes a factual description.
Outputs a CSV in the site schema.

Reads every "*Accidents.txt" in --datadir. NJDOT lat/lng are ignored (unreliable);
locations come from geocoding the intersection text. manual_overrides.json (optional,
{case_id: [lat, lng]}) places records that can't be geocoded to an intersection.
"""
import argparse, csv, glob, json, math, os, re, sys

ABBR = {" AVE": " Avenue", " ST": " Street", " RD": " Road", " PL": " Place",
        " DR": " Drive", " LN": " Lane", " CT": " Court", " PK": " Park"}

# NJTR-1 crash type code -> (schema crash_type, description phrase)
CT = {
    "01": ("vehicle", "rear-end collision"), "02": ("vehicle", "same-direction sideswipe"),
    "03": ("vehicle", "right-angle collision"), "04": ("vehicle", "opposite-direction collision"),
    "05": ("vehicle", "opposite-direction sideswipe"), "06": ("vehicle", "collision with a parked vehicle"),
    "07": ("vehicle", "left-turn / U-turn collision"), "08": ("vehicle", "backing collision"),
    "09": ("vehicle", "encroachment collision"), "10": ("other", "overturn"),
    "11": ("vehicle", "collision with a fixed object"), "12": ("other", "collision with an animal"),
    "13": ("pedestrian", "pedestrian crash"), "14": ("bicycle", "crash involving a bicyclist"),
    "15": ("other", "collision with a non-fixed object"), "16": ("other", "railcar collision"),
}
SEV = {"F": ("fatal", "Fatal"), "I": ("injury", "Injury"), "P": ("property_damage", "Property-damage")}
DIRDEG = {"N": (1, 0), "S": (-1, 0), "E": (0, 1), "W": (0, -1)}


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


def offset(lat, lng, dist_ft, direction):
    if not dist_ft or direction not in DIRDEG:
        return lat, lng
    dlat, dlng = DIRDEG[direction]
    lat += dlat * (dist_ft / 364000.0)
    lng += dlng * (dist_ft / (364000.0 * math.cos(math.radians(lat))))
    return round(lat, 6), round(lng, 6)


def g(p, i):
    return p[i].strip() if i < len(p) else ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--datadir", default=".")
    ap.add_argument("--municipality-name", default="HOPEWELL BORO", help="value in the data file")
    ap.add_argument("--municipality-label", default="Hopewell Borough", help="label written to output")
    ap.add_argument("--cache", default="geocode_cache.json")
    ap.add_argument("--overrides", default="manual_overrides.json")
    ap.add_argument("--out", default="njdot_rows.csv")
    args = ap.parse_args()

    geocache = json.load(open(args.cache)) if os.path.exists(args.cache) else {}
    overrides = json.load(open(args.overrides)) if os.path.exists(args.overrides) else {}
    files = sorted(glob.glob(os.path.join(args.datadir, "*Accidents.txt")))
    if not files:
        sys.exit(f"No *Accidents.txt found in {args.datadir}")

    rows = []
    for path in files:
        for line in open(path, encoding="latin-1"):
            p = [c.strip() for c in line.split(",")]
            if len(p) < 47 or p[2] != args.municipality_name:
                continue
            case = g(p, 0)[8:]
            mm, dd, yy = g(p, 3).split("/")
            t = g(p, 5).zfill(4)
            schema_type, ct_phrase = CT.get(g(p, 17), ("vehicle", "crash"))
            sev_schema, sev_word = SEV.get(g(p, 13), ("other", "Crash"))
            nveh = g(p, 18)
            loc_raw, cross_raw = g(p, 19), g(p, 38)
            dist, unit, direction = g(p, 35), g(p, 36), g(p, 37)
            at_int = unit == "AT" or not dist

            road_label = "Broad St (Route 518)" if loc_raw.startswith("ROUTE 518") else titlecase(loc_raw.split("/")[0])
            cross_label = titlecase(re.sub(r"ROUTE \d+ / ", "", cross_raw).split(" / ")[0]) if cross_raw else ""
            loc_label = (f"{road_label} & {cross_label}" if at_int else f"{road_label} near {cross_label}") if cross_label else road_label

            lat = lng = ""
            if case in overrides:
                lat, lng = overrides[case]
            else:
                for a in road_names(loc_raw):
                    for b in cross_names(cross_raw):
                        hit = geocache.get(f"{a}|{b}")
                        if hit:
                            lat, lng = hit[0], hit[1]
                            if not at_int:
                                lat, lng = offset(lat, lng, float(dist or 0), direction)
                            break
                    if lat:
                        break

            if schema_type in ("pedestrian", "bicycle"):
                who = "a pedestrian" if schema_type == "pedestrian" else "a bicyclist"
                desc = f"{sev_word} crash involving {who} and a vehicle on {road_label}"
            else:
                veh_txt = f"{nveh} vehicles" if nveh and nveh != "1" else "a vehicle"
                desc = f"{sev_word} {ct_phrase} involving {veh_txt} on {road_label}"
            if cross_label:
                desc += f" {'at' if at_int else f'about {dist} ft {direction} of'} {cross_label}"
            desc += ". (Source: NJDOT crash record.)"

            rows.append(dict(id=case, date=f"{yy}-{mm}-{dd}",
                             time=f"{t[:2]}:{t[2:]}" if t.strip("0") else "",
                             municipality=args.municipality_label, location=loc_label,
                             lat=lat, lng=lng, crash_type=schema_type, severity=sev_schema,
                             description=desc, source_url=""))
            print(f"  {case:15} {schema_type:10} {sev_schema:15} "
                  f"{('%s,%s' % (lat, lng)) if lat else 'NO-GEOCODE'}", file=sys.stderr)

    hdr = ["id", "date", "time", "municipality", "location", "lat", "lng",
           "crash_type", "severity", "description", "source_url"]
    with open(args.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=hdr); w.writeheader(); w.writerows(rows)
    ok = sum(1 for r in rows if r["lat"])
    print(f"\nWrote {len(rows)} rows ({ok} geocoded, {len(rows) - ok} need coords) -> {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
