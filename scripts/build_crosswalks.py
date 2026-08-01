#!/usr/bin/env python3
"""Build the crosswalk-inventory layer's data + web photos from the survey folder.

Input (the survey results folder, default:
  ~/Downloads/Hopewell Crosswalk Inventory - Results)
  map.geojson                     -- 41 location points + 72 photo points
  photo-intersection-matches.csv  -- one row per crossing, all the field detail.
                                     This is the editable source of truth: correct
                                     a reading by editing the row. `crossing_street`
                                     names the street each crossing spans, and a row
                                     with an empty `photo` is a crossing the surveyor
                                     reported without photographing.
  photos-jpeg/                    -- 760px JPEG conversions

Full-resolution HEIC originals, if you still have them, give much better popup
photos than the 760px JPEGs. The script looks for them in the sibling folder
"Hopewell Boro Crosswalk Inventory" and falls back to photos-jpeg/ otherwise.

Output (in the repo):
  data/crosswalks.json    -- one entry per location, photos nested
  photos/crosswalks/*.jpg -- downscaled copies the site actually loads

Unlike the crash data (which is read live from a Google Sheet), the crosswalk
inventory is a one-off survey, so it is baked into the repo. Re-run this script
if the survey is redone or corrected.

Usage:
  python3 scripts/build_crosswalks.py [path/to/results/folder] [path/to/originals]
"""

import csv
import json
import os
import shutil
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SRC = os.path.expanduser(
    "~/Downloads/Hopewell Crosswalk Inventory - Results")
DEFAULT_ORIGINALS = "Hopewell Boro Crosswalk Inventory"
OUT_JSON = os.path.join(REPO, "data", "crosswalks.json")
OUT_PHOTOS = os.path.join(REPO, "photos", "crosswalks")
MAX_PX = 1200  # long edge; keeps the whole set to a few MB


def stem(photo_name):
    """IMG_9815.HEIC -> IMG_9815"""
    return os.path.splitext(photo_name)[0]


def convert(src, dst):
    """Downscale (never upscale) and re-encode as JPEG with sips (macOS)."""
    try:
        info = subprocess.run(["sips", "-g", "pixelWidth", "-g", "pixelHeight", src],
                              check=True, capture_output=True, text=True).stdout
        long_edge = max(int(l.split(":")[1]) for l in info.splitlines()
                        if "pixel" in l)
        # -Z would happily upscale, which just wastes bytes.
        zoom = ["-Z", str(MAX_PX)] if long_edge > MAX_PX else []
        subprocess.run(
            ["sips"] + zoom + ["-s", "format", "jpeg",
             "-s", "formatOptions", "50", src, "--out", dst],
            check=True, capture_output=True)
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        print("  sips unavailable or failed (%s); copying as-is" % e)
        shutil.copyfile(src, dst)


def source_photo(name_stem, heic_dir, jpeg_dir):
    """Prefer the full-res HEIC original; fall back to the 760px JPEG."""
    if heic_dir:
        for ext in (".HEIC", ".heic"):
            p = os.path.join(heic_dir, name_stem + ext)
            if os.path.exists(p):
                return p
    p = os.path.join(jpeg_dir, name_stem + ".jpg")
    return p if os.path.exists(p) else None


# One scale, the surveyor's: a crossing is unmarked, or it is good / fair / bad.
# The CSV's `crosswalk` column also has a "faded" value, but every faded leg
# carries a condition too, so faded is just a bad or fair marking -- it earns no
# state of its own. Ordered worst first: an unmarked leg is the most actionable
# thing at a junction, so it is what the zoomed-out pin reports.
STATE_ORDER = ["unmarked", "bad", "fair", "good", "unknown"]
CONDITION_STATE = {"poor": "bad", "fair": "fair", "good": "good",
                   "like_new": "good"}


def leg_state(leg):
    if leg["crosswalk"] in ("none", ""):
        return "unmarked"
    # Marked, but nobody could grade it (an "unclear" reading, or a blank).
    return CONDITION_STATE.get(leg["condition"], "unknown")


def summarise(loc):
    """Roll the legs up into the location's headline figures. Computed here rather
    than read from map.geojson so that editing the CSV is all it takes to correct
    what the map shows."""
    legs = loc["photos"]
    for leg in legs:
        leg["state"] = leg_state(leg)

    loc["state"] = min((leg["state"] for leg in legs),
                       key=STATE_ORDER.index, default="unknown")
    loc["state_counts"] = {s: sum(1 for leg in legs if leg["state"] == s)
                           for s in STATE_ORDER
                           if any(leg["state"] == s for leg in legs)}
    styles = {leg["style"] for leg in legs} | {leg["style_secondary"] for leg in legs}
    loc["styles"] = "/".join(sorted(s for s in styles if s))


def main():
    src_dir = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SRC
    heic_dir = sys.argv[2] if len(sys.argv) > 2 else os.path.join(
        os.path.dirname(src_dir.rstrip("/")), DEFAULT_ORIGINALS)
    if not os.path.isdir(heic_dir):
        print("no HEIC originals at %s -- using the 760px JPEGs" % heic_dir)
        heic_dir = None
    geo_path = os.path.join(src_dir, "map.geojson")
    csv_path = os.path.join(src_dir, "photo-intersection-matches.csv")
    jpeg_dir = os.path.join(src_dir, "photos-jpeg")
    for p in (geo_path, csv_path, jpeg_dir):
        if not os.path.exists(p):
            sys.exit("missing input: %s" % p)

    rows = list(csv.DictReader(open(csv_path)))
    by_location = {}
    for r in rows:
        by_location.setdefault(r["intersection"], []).append(r)

    geo = json.load(open(geo_path))
    locations = []
    for f in geo["features"]:
        p = f["properties"]
        if p.get("kind") != "intersection":
            continue
        lng, lat = f["geometry"]["coordinates"]
        photos = []
        for r in sorted(by_location.get(p["name"], []), key=lambda r: r["taken"]):
            photos.append({
                # A row with no photo is a leg the surveyor reports from memory
                # rather than from a photograph; the site labels those as such.
                "file": stem(r["photo"]) + ".jpg" if r["photo"] else "",
                "street": r.get("crossing_street", ""),
                # Optional: which side of the junction, as a compass point. Only
                # needed where a street carries a crossing on both sides.
                "side": r.get("crossing_side", "").strip().upper(),
                "crosswalk": r["crosswalk"],
                "style": r["style"],
                "style_street": r["style_street"],
                "style_secondary": r["style_secondary"],
                "style_secondary_street": r["style_secondary_street"],
                "condition": r["condition"],
                "features": r["features"],
                "crosswalk_note": r["crosswalk_note"],
                "note": r["note"],
                "review_flag": r["review_flag"],
                "style_confidence": r["style_confidence"],
                "taken": r["taken"],
                "bearing": int(r["camera_bearing"]) if r["camera_bearing"] else None,
                "facing": r["camera_facing"],
                "stood_on_side": r["stood_on_side"],
                "meters_to_corner": r["meters_to_corner"],
                # where the photographer stood -- osm_crossings.py needs it to
                # tell which side of the junction a crossing is on
                "cam_lat": float(r["lat"]) if r["lat"] else None,
                "cam_lng": float(r["lng"]) if r["lng"] else None,
            })
        if not photos:
            print("  warning: no CSV rows for location %r" % p["name"])
        loc = {
            "name": p["name"],
            "lat": lat,
            "lng": lng,
            "jurisdiction": p.get("jurisdiction", ""),
            "county_route": p.get("county_route", ""),
            "needs_field_check": p.get("needs_field_check", ""),
            "photos": photos,
        }
        summarise(loc)
        locations.append(loc)

    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w") as fh:
        json.dump({
            "surveyed": "2026-07-31",
            "note": ("Visual inventory from photographs, one afternoon. Condition "
                     "grades are one reviewer's judgement by eye, not "
                     "retroreflectivity measurements. Absence from this list is "
                     "not evidence a crossing does not exist."),
            "locations": locations,
        }, fh, indent=1)
    print("wrote %s (%d locations)" % (OUT_JSON, len(locations)))

    os.makedirs(OUT_PHOTOS, exist_ok=True)
    n = 0
    for r in rows:
        if not r["photo"]:
            continue  # a leg the surveyor reported without photographing it
        s = stem(r["photo"])
        src = source_photo(s, heic_dir, jpeg_dir)
        if not src:
            print("  warning: no image found for %s" % s)
            continue
        convert(src, os.path.join(OUT_PHOTOS, s + ".jpg"))
        n += 1
    print("wrote %d photos to %s" % (n, OUT_PHOTOS))


if __name__ == "__main__":
    main()
