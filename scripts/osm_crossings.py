#!/usr/bin/env python3
"""Give every surveyed crossing real map geometry, from OpenStreetMap.

The survey recorded a junction node and the camera's bearing, which is enough to
place a marker but not to draw a crossing where it actually lies. OSM has better:
79 `footway=crossing` ways in the borough carry surveyed curb-to-curb geometry.
This script matches each survey photo to one of those ways where it can, and
falls back to deriving a crossing line from the road centreline where it can't
(unmarked legs, and marked crossings OSM doesn't have yet).

Run after build_crosswalks.py; it annotates data/crosswalks.json in place, adding
to each photo:

  geom        [[lat,lng],[lat,lng]]  curb-to-curb crossing line
  geom_source "osm" | "derived"      surveyed OSM geometry, or inferred
  geom_ref    OSM way id, when geom_source is "osm"

The raw Overpass response is cached in data/osm_roads.json so re-runs don't hit
the API. Delete that file to refresh from OSM.

Usage:
  python3 scripts/osm_crossings.py [--refresh]
"""

import json
import math
import os
import sys
import urllib.request

import build_crosswalks as bc

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
XWALK_JSON = os.path.join(REPO, "data", "crosswalks.json")
OSM_CACHE = os.path.join(REPO, "data", "osm_roads.json")

# Hopewell Borough plus a little margin.
BBOX = (40.3770, -74.7830, 40.4010, -74.7500)
OVERPASS = "https://overpass-api.de/api/interpreter"
QUERY = """[out:json][timeout:60];
(
  way["highway"](%f,%f,%f,%f);
  node["highway"="crossing"](%f,%f,%f,%f);
);
out body geom;
""" % (BBOX + BBOX)

# Matching thresholds. A crossing has to be near the junction, roughly square to
# the camera's line of sight, and in front of the camera rather than behind it.
MAX_DIST_M = 32
MAX_ALIGN_DEG = 55   # crossing heading vs camera bearing
MAX_FORWARD_DEG = 80  # camera bearing vs direction to the crossing

# Fallback carriageway widths (metres) when OSM has no width/lanes tag.
DEFAULT_WIDTH = {"secondary": 12.0, "tertiary": 11.0, "residential": 9.0,
                 "unclassified": 9.0, "service": 6.0, "track": 5.0}
ROAD_TYPES = set(DEFAULT_WIDTH)

R_EARTH = 6371000.0


# ---- geodesy (local flat-earth approximations; fine over a few hundred metres)


def m_per_deg(lat):
    return 111320.0, 111320.0 * math.cos(math.radians(lat))


def dist_m(a, b):
    mlat, mlng = m_per_deg((a[0] + b[0]) / 2)
    return math.hypot((a[0] - b[0]) * mlat, (a[1] - b[1]) * mlng)


def bearing(a, b):
    """Compass bearing a -> b, degrees clockwise from north."""
    mlat, mlng = m_per_deg((a[0] + b[0]) / 2)
    return math.degrees(math.atan2((b[1] - a[1]) * mlng,
                                   (b[0] - a[0]) * mlat)) % 360


def offset(pt, brg, metres):
    mlat, mlng = m_per_deg(pt[0])
    rad = math.radians(brg)
    return [pt[0] + metres * math.cos(rad) / mlat,
            pt[1] + metres * math.sin(rad) / mlng]


def ang_diff(a, b):
    """Smallest absolute difference between two bearings, 0-180."""
    return abs((a - b + 180) % 360 - 180)


def heading_diff(a, b):
    """Difference between two undirected headings, 0-90."""
    d = ang_diff(a, b)
    return min(d, 180 - d)


# ---- OSM data


def fetch_osm(refresh=False):
    if os.path.exists(OSM_CACHE) and not refresh:
        return json.load(open(OSM_CACHE))
    print("querying Overpass ...")
    req = urllib.request.Request(OVERPASS, data=QUERY.encode(),
                                 headers={"User-Agent": "hopewell-boro-crashes"})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.loads(r.read())
    os.makedirs(os.path.dirname(OSM_CACHE), exist_ok=True)
    with open(OSM_CACHE, "w") as fh:
        json.dump(data, fh)
    print("cached %d elements to %s" % (len(data["elements"]), OSM_CACHE))
    return data


def crossing_ways(osm):
    """OSM footway=crossing ways, as {id, line, mid, heading, markings}."""
    out = []
    for e in osm["elements"]:
        t = e.get("tags", {})
        if e["type"] != "way" or t.get("footway") != "crossing":
            continue
        geom = [[g["lat"], g["lon"]] for g in e.get("geometry", [])]
        if len(geom) < 2:
            continue
        out.append({
            "id": e["id"],
            "line": [geom[0], geom[-1]],
            "mid": [(geom[0][0] + geom[-1][0]) / 2,
                    (geom[0][1] + geom[-1][1]) / 2],
            "heading": bearing(geom[0], geom[-1]),
            # crossing:markings is the style tag; legacy crossing=zebra just
            # means "marked" and says nothing about style
            "markings": t.get("crossing:markings", ""),
            "taken": False,
        })
    return out


def annotate_crossing_streets(xways, roads):
    """Tag each OSM crossing way with the street it spans, so a photo whose CSV row
    names its leg can only match a crossing of that street."""
    named = [w for w in roads if w["tags"].get("name")]
    for x in xways:
        best = min(named, key=lambda w: local_heading(w, x["mid"])[1])
        x["street"] = best["tags"]["name"]


def road_ways(osm):
    """Drivable ways with geometry, for the derived-geometry fallback."""
    out = []
    for e in osm["elements"]:
        t = e.get("tags", {})
        if e["type"] != "way" or t.get("highway") not in ROAD_TYPES:
            continue
        geom = [[g["lat"], g["lon"]] for g in e.get("geometry", [])]
        if len(geom) < 2:
            continue
        out.append({"id": e["id"], "geom": geom, "tags": t,
                    "highway": t["highway"]})
    return out


def road_width(way):
    t = way["tags"]
    for key in ("width", "est_width"):
        try:
            return float(str(t[key]).split()[0])
        except (KeyError, ValueError):
            pass
    try:
        # ~3.3 m per lane plus a little for parking/shoulder
        return max(2, int(t["lanes"])) * 3.3 + 1.5
    except (KeyError, ValueError):
        return DEFAULT_WIDTH[way["highway"]]


def seg_dist_m(pt, a, b):
    """Perpendicular distance from pt to segment a-b, in metres. Measuring to the
    segment rather than to its midpoint matters here: OSM maps a whole street as
    one way with sparse vertices, so a midpoint can be 50 m from a junction the
    road runs straight through."""
    mlat, mlng = m_per_deg(pt[0])
    px, py = (pt[1] - a[1]) * mlng, (pt[0] - a[0]) * mlat
    bx, by = (b[1] - a[1]) * mlng, (b[0] - a[0]) * mlat
    seg2 = bx * bx + by * by
    t = 0.0 if seg2 == 0 else max(0.0, min(1.0, (px * bx + py * by) / seg2))
    return math.hypot(px - t * bx, py - t * by)


def project_to_way(way, pt):
    """Closest point on the way to pt. Survey junction nodes are OSM nodes, but
    not always the road's own node, so derived crossings are built from the
    projection onto the centreline rather than from the node itself."""
    best = None
    for i in range(len(way["geom"]) - 1):
        a, b = way["geom"][i], way["geom"][i + 1]
        mlat, mlng = m_per_deg(pt[0])
        px, py = (pt[1] - a[1]) * mlng, (pt[0] - a[0]) * mlat
        bx, by = (b[1] - a[1]) * mlng, (b[0] - a[0]) * mlat
        seg2 = bx * bx + by * by
        t = 0.0 if seg2 == 0 else max(0.0, min(1.0, (px * bx + py * by) / seg2))
        cand = [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]
        d = dist_m(pt, cand)
        if best is None or d < best[0]:
            best = (d, cand)
    return best[1]


def midpoint(line):
    return [(line[0][0] + line[1][0]) / 2, (line[0][1] + line[1][1]) / 2]


def local_heading(way, pt):
    """Heading of the way's segment nearest pt, and that segment's distance."""
    best = None
    for i in range(len(way["geom"]) - 1):
        a, b = way["geom"][i], way["geom"][i + 1]
        d = seg_dist_m(pt, a, b)
        if best is None or d < best[0]:
            best = (d, bearing(a, b))
    return best[1], best[0]


# ---- matching


def match_osm(locations, xways):
    """Greedily pair each marked-crossing photo with the OSM crossing way that
    best fits its junction and camera bearing. Best-scoring pairs win first, so
    an unambiguous match can't be stolen by a marginal one."""
    pairs = []
    for loc in locations:
        node = [loc["lat"], loc["lng"]]
        for p in loc["photos"]:
            # An unmarked leg has no marking to align to; OSM crossing ways are
            # crossings that exist, so matching one to it would be wrong.
            if p["crosswalk"] == "none":
                continue
            # Without a camera bearing the sightline checks can't run, but a leg
            # that names its street doesn't need them -- that's how a crossing
            # nobody photographed still lands on its OSM line.
            if p.get("bearing") is None and not p.get("street"):
                continue
            for w in xways:
                d = dist_m(node, w["mid"])
                if d > MAX_DIST_M:
                    continue
                if p.get("street"):
                    # The CSV names the leg, which beats anything inferred from a
                    # camera bearing or a GPS fix -- take the nearest OSM crossing
                    # of that street and skip the sightline checks entirely. A
                    # named side still has to hold, or a crossing pinned to one
                    # side of a junction could silently snap to the other.
                    if w["street"] != p["street"]:
                        continue
                    if p.get("side") in COMPASS and ang_diff(
                            bearing(node, w["mid"]), COMPASS[p["side"]]) > 67:
                        continue
                    pairs.append((d, loc, p, w))
                    continue
                align = heading_diff(w["heading"], p["bearing"])
                if align > MAX_ALIGN_DEG:
                    continue
                cam = [p["cam_lat"], p["cam_lng"]]
                fwd = ang_diff(bearing(cam, w["mid"]), p["bearing"])
                if fwd > MAX_FORWARD_DEG:
                    continue
                pairs.append((d + 0.6 * align + 0.4 * fwd, loc, p, w))

    pairs.sort(key=lambda x: x[0])
    for _score, _loc, p, w in pairs:
        if p.get("geom") or w["taken"]:
            continue
        w["taken"] = True
        p["geom"] = w["line"]
        p["geom_source"] = "osm"
        p["geom_ref"] = w["id"]


COMPASS = {"N": 0, "NE": 45, "E": 90, "SE": 135,
           "S": 180, "SW": 225, "W": 270, "NW": 315}

MERGE_DIST_M = 6


def separate_conflicting_legs(locations, roads):
    """No two crossings that disagree may occupy the same spot.

    A crossing is either marked or it isn't; the same piece of road cannot be
    both. When two legs of a junction land on top of each other with different
    verdicts, at least one of them is on the wrong leg -- the CSV's
    `crossing_street` was guessed rather than surveyed, or the photo was assigned
    to the wrong corner. Rather than draw a contradiction, move the weaker-evidenced
    leg to the best free position at the junction: the other side of its own
    street first, then a street with no crossing on it yet.

    Legs that agree are left alone -- those are the same crossing photographed
    twice, and merge_duplicate_legs folds them together.
    """
    moved, stuck = [], []
    for loc in locations:
        node = [loc["lat"], loc["lng"]]
        near = [(d, h, w) for d, h, w in
                ((local_heading(w, node)[1], local_heading(w, node)[0], w)
                 for w in roads) if d < 40]
        if not near:
            continue
        # Strongest evidence keeps its position: an OSM-surveyed line, then a
        # photographed leg, then one merely reported.
        order = sorted(loc["photos"],
                       key=lambda p: (p.get("geom_source") != "osm", not p["file"]))
        placed = []
        for leg in order:
            if not leg.get("geom"):
                continue
            if not _clashes(leg, placed):
                placed.append(leg)
                continue
            better = _free_position(loc, leg, placed, near)
            if better:
                geom, way = better
                moved.append((loc["name"], leg["file"] or "reported leg",
                              leg.get("geom_road"), way["tags"].get("name")))
                leg["geom"] = geom
                leg["geom_road"] = way["tags"].get("name", "")
                leg["geom_source"] = "derived"
                leg["moved_off_conflict"] = True
                leg.pop("geom_ref", None)
            else:
                stuck.append((loc["name"], leg["file"] or "reported leg"))
            placed.append(leg)
    for name, photo, was, now in moved:
        print("  moved %s at %s off a contradicting crossing: %s -> %s"
              % (photo, name, was, now))
    for name, photo in stuck:
        print("  warning: %s at %s contradicts another crossing and has nowhere "
              "else to go -- fix crossing_street" % (photo, name))
    return len(moved)


def _clashes(leg, placed):
    """Same spot, different verdict."""
    return any(q["crosswalk"] != leg["crosswalk"]
               and dist_m(midpoint(q["geom"]), midpoint(leg["geom"])) < MERGE_DIST_M
               for q in placed)


def _free_position(loc, leg, placed, near):
    """Best position at this junction that contradicts nothing already drawn."""
    node = [loc["lat"], loc["lng"]]
    own = leg.get("geom_road") or leg.get("street")
    taken = [midpoint(q["geom"]) for q in placed]
    # The location's name lists the streets that meet here; a crossing at this
    # junction is on one of them, not on a street a block away that happens to
    # fall inside the search radius.
    junction_streets = {s.strip() for s in loc["name"].split("&")}
    options = []
    for _d, road_hdg, way in near:
        name = way["tags"].get("name") or ""
        if junction_streets and name not in junction_streets:
            continue
        for side in (road_hdg, (road_hdg + 180) % 360):
            geom = crossing_line(node, way, road_hdg, near, leg, taken, side=side)
            centre = midpoint(geom)
            if local_heading(way, centre)[1] >= 3.0:
                continue  # off the end of the road
            clash = any(q["crosswalk"] != leg["crosswalk"]
                        and dist_m(midpoint(q["geom"]), centre) < MERGE_DIST_M
                        for q in placed)
            if clash:
                continue
            occupied = any(dist_m(midpoint(q["geom"]), centre) < MERGE_DIST_M
                           for q in placed)
            # Prefer: its own street, then an unoccupied leg, then the side most
            # square to the camera's line of sight.
            sightline = (abs(90 - heading_diff(road_hdg, leg["bearing"]))
                         if leg.get("bearing") is not None else 0)
            options.append((name != own, occupied, sightline, geom, way))
    if not options:
        return None
    options.sort(key=lambda o: o[:3])
    return options[0][3], options[0][4]


def merge_duplicate_legs(locations):
    """Collapse legs that are the same crossing photographed more than once.

    The CSV is one row per photograph, and the surveyor often shot a crossing from
    two corners, so three photos of the Hart Ave crossing became three lines
    stacked on top of each other. Legs merge only when they span the same street,
    sit within a few metres of each other, and agree on the verdict -- two legs
    that disagree are a real error (a photo assigned to the wrong leg), and
    merging those would bury it instead of showing it.
    """
    merged = 0
    for loc in locations:
        keep = []
        for leg in loc["photos"]:
            twin = next(
                (k for k in keep
                 if k.get("geom_road") == leg.get("geom_road")
                 and k["crosswalk"] == leg["crosswalk"]
                 and k.get("geom") and leg.get("geom")
                 and dist_m(midpoint(k["geom"]), midpoint(leg["geom"])) < MERGE_DIST_M),
                None)
            if twin is None:
                keep.append(leg)
                continue
            # Keep the better-evidenced line, carry the other photo along with it.
            if twin["geom_source"] != "osm" and leg["geom_source"] == "osm":
                leg["also"] = twin.pop("also", []) + [twin]
                keep[keep.index(twin)] = leg
            else:
                twin.setdefault("also", []).append(leg)
            merged += 1
    # `also` legs are nested inside their primary, so drop them from the top level
    for loc in locations:
        nested = {id(x) for p in loc["photos"] for x in p.get("also", [])}
        loc["photos"] = [p for p in loc["photos"] if id(p) not in nested]
    return merged


def name_crossed_road(locations, roads):
    """Record the street each crossing spans. Corrections are written per street
    ("the Hart Ave leg is unmarked"), so every leg needs to know which one it is;
    the derived branch knows already, OSM matches don't."""
    named = [w for w in roads if w["tags"].get("name")]
    for loc in locations:
        for p in loc["photos"]:
            if not p.get("geom") or p.get("geom_road"):
                continue
            mid = [(p["geom"][0][0] + p["geom"][1][0]) / 2,
                   (p["geom"][0][1] + p["geom"][1][1]) / 2]
            best = min(named, key=lambda w: local_heading(w, mid)[1])
            p["geom_road"] = best["tags"]["name"]


def derive(locations, roads):
    """Draw a crossing line from the road centreline for every photo that didn't
    match an OSM crossing way -- the unmarked legs, and marked crossings OSM
    hasn't got yet. Approximate by construction, and flagged as such."""
    for loc in locations:
        node = [loc["lat"], loc["lng"]]
        near = []
        for w in roads:
            hdg, d = local_heading(w, node)
            if d < 40:
                near.append((d, hdg, w))
        if not near:
            continue
        for p in loc["photos"]:
            if p.get("geom"):
                continue
            named = [x for x in near if x[2]["tags"].get("name") == p.get("street")]
            if named:
                # The CSV says which leg this is; believe it.
                crossed = min(named, key=lambda x: x[0])
            elif p.get("bearing") is not None:
                # No street recorded: you photograph a crossing face-on, so the
                # road being crossed is the one most square to the camera -- but
                # it has to be a road at this junction, so distance carries real
                # weight. Without that, a road 20 m away can win on angle alone.
                crossed = min(near, key=lambda x: abs(90 - heading_diff(
                    x[1], p["bearing"])) + x[0] * 1.5)
            else:
                print("  warning: cannot place %s at %s (no street, no bearing)"
                      % (p["file"] or "reported leg", loc["name"]))
                continue
            _d, road_hdg, way = crossed
            avoid = [midpoint(q["geom"]) for q in loc["photos"]
                     if q is not p and q.get("geom")]
            p["_loc"] = loc["name"]
            p["geom"] = crossing_line(node, way, road_hdg, near, p, avoid)
            p["geom_source"] = "derived"
            p["geom_road"] = way["tags"].get("name", "")


def crossing_line(node, way, road_hdg, near, leg, avoid, side=None):
    """One crossing of `way` at this junction, as a curb-to-curb line.

    Perpendicular to the road, one carriageway long, sitting beside the junction
    box rather than in it. `avoid` are midpoints of crossings already placed here,
    used to pick a side when the photograph doesn't settle it.
    """
    width = road_width(way)

    # Walk across the road: perpendicular to it, along the camera's line of sight
    # where there is one.
    ref = leg["bearing"] if leg.get("bearing") is not None else road_hdg + 90
    path = min((road_hdg + 90) % 360, (road_hdg - 90) % 360,
               key=lambda h: ang_diff(h, ref))

    others = [x for x in near if x[2] is not way]
    clear = (max(road_width(x[2]) for x in others) / 2 + 2.5) if others else 6.0
    base = project_to_way(way, node)

    if side is not None:
        centre = offset(base, side, clear)
        return [offset(centre, path, -width / 2), offset(centre, path, width / 2)]

    # The CSV can name the side as a compass point ("the crossing on the south
    # side of Princeton"), which is the only way to tell two crossings of the
    # same street apart.
    if leg.get("side") in COMPASS:
        want = COMPASS[leg["side"]]
        h = min((road_hdg, (road_hdg + 180) % 360),
                key=lambda c: ang_diff(c, want))
        centre = offset(base, h, clear)
        if local_heading(way, centre)[1] >= 3.0:
            print("  warning: %s side of %s is off the end of the road at %s"
                  % (leg["side"], way["tags"].get("name"), leg.get("_loc", "")))
        return [offset(centre, path, -width / 2), offset(centre, path, width / 2)]

    # Which side of the junction? Only sides where the road actually continues
    # will do -- at a T-junction one of them is off the end of the road, and a
    # crossing there would float in open ground. Among the valid sides, take the
    # one the photographer was standing on; with no photograph, the one furthest
    # from the crossings already placed here.
    if leg.get("cam_lat") is not None:
        cam = [leg["cam_lat"], leg["cam_lng"]]
        along = dist_m(base, cam) * math.cos(
            math.radians(ang_diff(bearing(base, cam), road_hdg)))
        first = road_hdg if along >= 0 else (road_hdg + 180) % 360
        rank = lambda h, cand: (h != first, 0)  # noqa: E731
    else:
        first = road_hdg
        rank = lambda h, cand: (  # noqa: E731
            0, -min((dist_m(cand, m) for m in avoid), default=999))
    options = []
    for h in (first, (first + 180) % 360):
        cand = offset(base, h, clear)
        options.append((local_heading(way, cand)[1] >= 3.0,) + rank(h, cand) + (cand,))
    options.sort()
    centre = options[0][-1]
    return [offset(centre, path, -width / 2), offset(centre, path, width / 2)]


def main():
    refresh = "--refresh" in sys.argv[1:]
    data = json.load(open(XWALK_JSON))
    locations = data["locations"]

    # The camera's own GPS fix, needed to tell front from back and left from
    # right. build_crosswalks.py carries it through as cam_lat/cam_lng.
    missing = [p for loc in locations for p in loc["photos"]
               if "cam_lat" not in p]
    if missing:
        sys.exit("crosswalks.json has no cam_lat/cam_lng -- re-run "
                 "build_crosswalks.py first")

    osm = fetch_osm(refresh)
    xways = crossing_ways(osm)
    roads = road_ways(osm)
    annotate_crossing_streets(xways, [w for w in roads
                                      if w["highway"] != "service"])
    print("OSM: %d crossing ways, %d road ways" % (len(xways), len(roads)))

    for loc in locations:
        for p in loc["photos"]:
            p.pop("geom", None)
            p.pop("geom_source", None)
            p.pop("geom_ref", None)
            p.pop("geom_road", None)

    for loc in locations:
        for p in loc["photos"]:
            p.pop("_loc", None)
    match_osm(locations, xways)
    derive(locations, roads)
    name_crossed_road(locations, [w for w in roads if w["highway"] != "service"])
    separated = separate_conflicting_legs(
        locations, [w for w in roads if w["highway"] != "service"])
    merged = merge_duplicate_legs(locations)
    # Merging changes how many crossings a location has, so its roll-up has to be
    # recomputed -- otherwise the popup counts legs that are no longer drawn.
    for loc in locations:
        bc.summarise(loc)

    photos = [p for loc in locations for p in loc["photos"]]
    counts = {"osm": 0, "derived": 0, "none": 0}
    for p in photos:
        counts[p.get("geom_source", "none")] += 1
    print("geometry: %d from OSM, %d derived, %d without" %
          (counts["osm"], counts["derived"], counts["none"]))
    print("merged %d duplicate legs (same crossing, several photos)" % merged)
    print("moved %d legs off a contradicting crossing" % separated)

    for loc in locations:
        for p in loc["photos"]:
            p.pop("_loc", None)
    with open(XWALK_JSON, "w") as fh:
        json.dump(data, fh, indent=1)
    print("updated %s" % XWALK_JSON)


if __name__ == "__main__":
    main()
