# Hopewell Area Crash Map — Setup Guide

A single-file replacement for the Google My Maps crash map, built with Leaflet.
No server, no database — the "backend" is a Google Sheet, so anyone comfortable
with spreadsheets can maintain the data with no code involved.

Open `index.html` in a browser and it reads live from the published Google
Sheet — that Sheet is the site's single source of truth. No crash data is baked
into the HTML; if the Sheet can't be reached, the map shows a visible "data
unavailable" state rather than stale data. Sections 1 and 2 are about
maintaining that crash data; section 3 covers the separate crosswalk inventory
layer, which is static survey data stored in the repo.

> **Note:** Google caches the "Publish to web" CSV, so edits to the Sheet can
> take a few minutes to show up on the live site.
>
> `template.csv` holds the five real crash records (all at the Broad St &
> Greenwood Ave intersection) as a reference/import file. The police reports
> don't record lat/lng, so those five pins are placed in a small spread around
> the Broad/Greenwood signal (each keyed to the leg named in its report) so
> every marker stays clickable.

## 1. Set up the data source (Google Sheet)

1. Open your Google Sheet, delete the old sample rows, and import `template.csv`
   (File → Import → Upload → "Replace current sheet" or "Append"), or just
   copy/paste its contents. `template.csv` already contains the five real crash
   records with the correct column headers — add new rows below them as more
   reports come in.
2. Column reference:

   | Column | Required | Notes |
   |---|---|---|
   | `id` | yes | Any unique number or code per row |
   | `date` | yes | `YYYY-MM-DD` |
   | `time` | no | 24-hour `HH:MM`, e.g. `17:40` |
   | `municipality` | yes | `Hopewell Borough` — this site covers the Borough only; shown in the popup |
   | `location` | yes | Street / intersection name shown in the popup title |
   | `lat` | yes | Decimal latitude |
   | `lng` | yes | Decimal longitude |
   | `crash_type` | yes | One of: `bicycle`, `pedestrian`, `vehicle`, `other` |
   | `severity` | yes | One of: `fatal`, `injury`, `property_damage` |
   | `description` | no | One or two sentences, shown in the popup — see the privacy note below |
   | `source_url` | no | Optional link (e.g. to a public NJDOT crash record page). Leave blank if none. |

   **Getting lat/lng:** right-click a location on Google Maps → the coordinates
   are the first thing in the context menu, click to copy. Or use
   https://www.latlong.net/.

3. Publish the sheet as CSV: **File → Share → Publish to web** → under
   "Link", choose the specific sheet/tab → set the format dropdown to
   **Comma-separated values (.csv)** → **Publish**. Copy the link it gives you.
4. This is **already done** — `index.html` has `DATA_URL` set to your published
   link near the top of the `<script>` block:

   ```js
   const DATA_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-.../pub?output=csv";
   ```

   The map reads live from the Sheet — anyone with edit access can add,
   correct, or remove crashes, and the site picks it up on next page load.
   No redeploy needed for data changes. If you ever re-publish under a new
   link, paste the new one between those quotes and save.

## 2. A note on privacy

Actual police crash reports typically include names, home addresses, and
license plate numbers of the people involved. I'd strongly recommend keeping
`description` to a neutral, factual summary (what happened, contributing
factor if known) rather than linking directly to a scanned report PDF, unless
that report has been redacted first. If you do want to link source documents
(e.g. for the councilperson or PBSAC's internal use), consider a second,
non-public sheet/version rather than exposing them through `source_url` on
the public site.

## 3. The crosswalk inventory layer

The **Crosswalk inventory** checkbox (under "Other layers", off by default) shows
**84 crossings at 44 locations**, from the survey walked on 31 July 2026 and
corrected by the surveyor afterwards.

| | Good | Fair | Bad | Unmarked |
|---|---|---|---|---|
| Crossings | 22 | 32 | 10 | 20 |
| Locations (worst leg) | 11 | 10 | 5 | 18 |

18 of the 44 locations have at least one unmarked leg, and 8 have no markings at
all. 63 crossings are backed by a photograph; the other 21 the surveyor reported
without photographing.

From zoom 17 in, each surveyed crossing is **drawn to scale where it actually
lies** — across the carriageway, square to the road centreline, with the markings
in the style that was recorded: two edge lines for transverse "parallel lines",
rungs for continental, both for ladder, and a dashed empty corridor where there
is no marking at all. Zoomed further out the crossings are too small to read, so
the layer falls back to one icon per location.

**Colour is condition, on one scale: Good, Fair, Bad, or Unmarked.** Each crossing
is coloured by its own grade, so a good crossing beside an unmarked leg reads as
one of each rather than as a single averaged colour. The zoomed-out pin takes the
location's **worst** leg — an unmarked leg counts as worst, since a missing
crossing is the most actionable thing at a junction — and where the legs differ
the popup spells the mix out ("1 unmarked, 1 fair") instead of calling it "mixed".

The CSV's `crosswalk` column also carries a `faded` value, but it earns no state
of its own: every faded leg records a condition too, so faded is just a fair or
bad marking. `condition: like_new` folds into Good.

Clicking any crossing shows the photo of its actual condition; clicking the photo
opens it full size, and locations with more than one photo show the rest as
thumbnails.

Unlike the crash data, this is a one-off survey rather than a living dataset, so
it is baked into the repo instead of read from a Sheet:

| Path | What it is |
|---|---|
| `data/crosswalks.json` | One entry per location, photos and field detail nested |
| `photos/crosswalks/*.jpg` | The 72 survey photos, downscaled to 1200px for the web |
| `data/osm_roads.json` | Cached Overpass response: borough road + crossing geometry |
| `scripts/build_crosswalks.py` | Regenerates the data and photos from the survey folder |
| `scripts/osm_crossings.py` | Adds the map geometry each crossing is drawn from |

To rebuild after a re-survey or a correction, run both, in this order:

```bash
python3 scripts/build_crosswalks.py "~/Downloads/Hopewell Crosswalk Inventory - Results" && python3 scripts/osm_crossings.py
```

`build_crosswalks.py` reads `map.geojson` and `photo-intersection-matches.csv`
from the survey folder, and prefers the full-resolution HEIC originals (looked
for in a sibling folder named `Hopewell Boro Crosswalk Inventory`) over the 760px
JPEG conversions.

### Correcting the data

`photo-intersection-matches.csv` in the survey folder is the editable source of
truth — it started as one agent's read of the photographs, so expect to correct
it. Edit the row and rebuild; there is no separate corrections file.

| Column | What to change it to |
|---|---|
| `crosswalk` | `yes`, `faded`, `none`, `unclear` |
| `style` | `parallel_lines`, `continental`, `ladder`, or blank when unmarked |
| `condition` | `poor`, `fair`, `good`, `like_new`, or blank when unmarked. This is what the map colours: poor → Bad, fair → Fair, good/like_new → Good |
| `crossing_street` | The street this crossing spans, exactly as OSM names it. This is what puts the line on the right leg of the junction — change it if a crossing is drawn across the wrong street |
| `crossing_side` | Optional compass point (`N`/`NE`/`E`/…) for which side of the junction the crossing sits on. Only needed where one street carries a crossing on both sides — "the crossing on the south side of Princeton". Left blank, the side is inferred from where the photographer stood |
| `crosswalk_note` | Free text, shown in the popup caption |

**A junction in the wrong place** is fixed in `map.geojson`, not the CSV — that
file holds each location's coordinates. This has happened once: the survey put
"Lafayette Street & North Elm Street" 143 m from where those streets actually
meet, because Lafayette crosses North Elm at *two* junctions and the photo
matching averaged one photo from each into a single point in open ground. The fix
was to correct the coordinate and add a second location,
`Lafayette Street & North Elm Street (east, at Kings Path)`, then point one photo
at each. If crossings at some junction are drawn in open ground or nowhere near
the street, suspect the coordinate before the crossing.

A crossing nobody photographed goes in as a row with **`photo` left empty**, plus
`intersection`, `crossing_street`, `crosswalk`, `style`, `condition`, and
`crossing_side` where the street has two. The site
lists those separately as "reported by the surveyor, not photographed", and the
popup header counts legs and photos apart, so an unphotographed leg never passes
as photographic evidence. Each leg's Good/Fair/Bad/Unmarked state, and the
location's roll-up of them, are recomputed from the CSV on every build, so
correcting a row is enough — nothing else needs touching.

### Where the crossing lines come from

The survey itself recorded a junction node and a camera bearing — enough to place
a pin, not enough to draw a crossing. `osm_crossings.py` gets the geometry from
OpenStreetMap instead, via one cached Overpass query (pass `--refresh`, or delete
`data/osm_roads.json`, to re-query):

- **60 of the 84 crossings match an OSM `footway=crossing` way**, which carries
  its own curb-to-curb line. The match must be within 32 m of the junction, and
  where the row names a `crossing_street` — optionally a `crossing_side` too —
  only an OSM crossing of that street and side will do. Where the row names no
  street, the camera stands in for it: the crossing has to be roughly square to
  the view and in front of the camera rather than behind it. Best-scoring pairs
  are assigned first, and one OSM way can only be used once.
- **The other 24 are derived** from the road centreline: perpendicular to
  `crossing_street` (or, where that is blank, to whichever road is most square to
  the camera), one carriageway wide (from OSM `width`/`lanes` where tagged, else a
  default for the road class), sitting beside the junction box on the side the
  photographer was standing. This covers the unmarked legs — which have no OSM
  crossing way by definition — the crossings OSM hasn't got yet, and the legs
  reported without a photograph.

Which of the two a line came from is kept in the JSON as `geom_source`, but the
map doesn't distinguish them, and deliberately so: most OSM crossing ways here are
traced from aerial imagery rather than surveyed, several run sidewalk-to-sidewalk
rather than curb-to-curb, and a derived line pinned to the centreline with a
tagged carriageway width is often the closer of the two. Neither says anything
about whether the crossing exists — that comes from the photograph.

**Every line's position is approximate to within a few metres**, whichever source
it came from: a derived line's position along the road is an estimate, and on a
skewed junction the side it lands on comes partly from the photo's GPS fix. Don't
scale measurements off them. What is solid is which street each crossing spans and
which junction it belongs to; every line was checked to span exactly one road
centreline, and the street its row names, at a median of 7 m from the junction.

The CSV has one row per photograph, and the surveyor often shot the same crossing
from two corners, so **rows that land on the same crossing are merged into one
line**: same street, within 6 m, and agreeing on the verdict. The extra photos ride
along and show up as thumbnails, which is why a popup can read "2 legs · 4 photos".
Today 72 photos and 21 reported legs resolve to 84 crossings.

**Two crossings that disagree can never occupy the same spot.** A stretch of road
is either marked or it isn't, so a marked and an unmarked crossing drawn on top of
each other is always an error in the data — usually `crossing_street` naming the
wrong leg. `separate_conflicting_legs` enforces this: the better-evidenced line
holds its position (an OSM-matched line first, then a photographed leg, then one
merely reported) and the other is moved to the best free position at the junction —
the other side of its own street if that works, otherwise a street at the junction
with no crossing on it yet. Candidates are restricted to the streets named in the
location's own name, so a crossing can't jump to a road a block away. The build
prints every move it makes, and warns if a leg has nowhere non-contradictory to go.

A moved leg is marked `moved_off_conflict` in the JSON. Treat those as prompts:
the script picked the most plausible free spot, but the surveyor is the one who
knows which leg the photo actually shows, and setting `crossing_street` correctly
makes the move unnecessary.

On the map, **dashed means one thing: nothing is painted there.** An unmarked leg
is drawn as an empty corridor outline, so an absence reads as an absence rather
than as missing data.

Crossing and road geometry is © OpenStreetMap contributors, ODbL — the same
attribution already shown on the map.

**Two caveats worth repeating to anyone reading the layer:**

- **Condition grades are one reviewer's judgement by eye from a single
  photograph**, not retroreflectivity measurements, and absence from the layer
  is not evidence that a crossing doesn't exist or is fine. The survey folder's
  `LIMITATIONS.md` is the full version and is worth reading before any of this
  goes to the county engineer. Locations with a flagged call show an orange
  "needs a field check" note in the popup.
- **Every crossing's position is approximate to within a few metres** — see "Where
  the crossing lines come from" above. What street it spans and which junction it
  belongs to are reliable; its exact placement is not.

### When each street was last repaved

`data/paving.json` records when a street was last resurfaced, and is **hand-maintained
desk research, not part of the survey** — the surveyor never observed this. It is a
separate file for that reason, and `build_crosswalks.py` folds it into
`crosswalks.json` at build time, so the site needs no second fetch. Each leg gets a
`repaved` object (or `null`), and each location gets a `repaved` list plus
`repaved_unknown` — the streets at that junction with no date on record.

Popups show the year, the age, the source with a link, and when the street would
next come due.

**There is no public dataset of last-repaved dates for municipal streets.** Every
entry traces to a named grant award or a published construction notice:

| Street | Last repaved | Source |
|---|---|---|
| North Greenwood Avenue | 2019 | NJDOT Municipal Aid, FY2019, $392,260 |
| Columbia Avenue | 2020 | NJDOT Municipal Aid, FY2020, $238,465 |
| Railroad Place | 2021 | NJDOT Municipal Aid, FY2021, $282,290 |
| Mercer Street, Walnut Street (and Newell Place) | 2022 | NJDOT Municipal Aid, FY2022, $385,000 |
| Hart Avenue | 2024 | NJDOT Municipal Aid, FY2023 $310,630 + FY2024 Phase 2 $382,968 |
| East Broad Street | 2024 | Mercer County milling and resurfacing of CR 518, began 19 Aug 2024, **Elm Street to Greenwood Avenue only** |

**That is 7 of the 35 streets carrying a surveyed crossing.** The other 28 are
unknown — including West Broad Street, where the worst conditions are. Three things
to know before leaning on any of it:

- A grant **award** year is not a construction year. Municipal Aid money is usually
  built the following season or the one after, so treat those as "no earlier than".
- Dates are recorded **per street**, but paving happens per segment. East Broad's
  entry carries a `limits` field for exactly this reason.
- **Absence of a date says nothing about condition.** It means nobody looked it up.

To fill the gap: ask the **Borough Clerk** for the engineer's paving history, and —
if the borough has one — the **road-opening moratorium list**, which many NJ
municipalities keep for five years after resurfacing and which is therefore a
recent-paving list already written down. For CR 518 west of Greenwood, ask the
**County Engineer**.

`data/paving.json` also holds the **cycle assumptions** used to estimate "next due",
and both are flagged `NOT VERIFIED` in the file itself. Mercer County describes a
condition-driven pavement management system over 180 centerline miles and publishes
no cycle length or forward schedule; 10 years is used as the low end of the standard
10–20 year service life for a full mill-and-overlay. The borough publishes no
pavement management programme at all, and at roughly one grant-funded street per
year against 35+ streets its de facto cycle is far longer than the 15 years assumed.
Neighbouring Hopewell Township prioritises roads by the probability they stay in good
shape for 10–15 years, which is the closest local benchmark found. **Confirm both
with the engineers before quoting either.**

### Repaving priority — the "top 5" list

The **Repaving priority** checkbox scores every surveyed location and lists the top
five. Turning it on turns the crosswalk layer on too; clicking an entry zooms to it
and opens its popup. The score is computed in the browser, not baked in, because the
crash half of it comes from the live Sheet.

It is deliberately a simple additive score, so it can be argued with:

| Term | Weight |
|---|---|
| **Crash harm**, per crash within 40 m | Pedestrian or cyclist: fatal 12, injury 6, property damage 2. Vehicle only: fatal 4, injury 2, property damage 0.5 |
| **Survey deficiency**, per leg | Unmarked 3, bad 2, fair 0.5, good 0, marked-but-ungraded 1 |
| **Paving timing**, per location | +3 where a street repaved within 3 years now has an unmarked or bad crossing — the markings went with the paving, which is cheap to restore and easy to justify |
| | ×0.6 where a street is at or past its assumed cycle — **don't paint a road that's about to be milled** |

Harm is the heaviest term on purpose: **a worn crossing where someone was injured
outranks a worn crossing where nobody has been**, and a person hurt outside a vehicle
counts for roughly double one inside it.

Three limits are printed in the panel itself and belong in any presentation of it:

- **Proximity is not causation.** A crash within 40 m of a junction was not
  necessarily at the crosswalk, and the crash set is small.
- **The paving term can only apply to 15 of the 44 locations**, so it cannot
  meaningfully reorder the rest. Until the coverage gap above is filled, this ranks
  partly by which streets happen to have a documented year.
- **The borough already holds a $1.51M Safe Routes to School award** (2024, plus up
  to $750k design) whose scope includes upgrading multiple crosswalks and RRFBs on
  Broad Street. Check this list against that project's design before recommending
  anything — some of the top entries may already be funded.

Because the layer is loaded with `fetch`, it needs to be served over HTTP —
opening `index.html` straight off the filesystem will show the crash pins but
not the crosswalks. To check it locally:

```bash
python3 -m http.server 8000
```

## 4. Deploying (GitHub Pages)

It's one HTML file with no build step, and the repo already lives on GitHub, so
GitHub Pages is the simplest host. `index.html` is at the repo root, which is
what Pages serves as the home page.

1. Push the latest files to the `main` branch:

   ```sh
   git add -A
   git commit -m "Deploy crash map"
   git push origin main
   ```
2. On GitHub, go to the repo → **Settings** → **Pages** (left sidebar).
3. Under **Build and deployment** → **Source**, pick **Deploy from a branch**.
4. Set **Branch** to `main` and the folder to **`/ (root)`**, then **Save**.
5. Wait ~1 minute. Your site will be live at:

   **https://bedrockdude10.github.io/hopewell-boro-crashes/**

   (Pages shows the exact URL at the top of that same settings page once it's
   built.)

**Notes:**

- On the free plan the repo must be **public** for Pages to work. That's fine
  here — the data is already public (a published Sheet with no personal
  details).
- **Crash data changes need no redeploy.** Editing the Google Sheet updates the
  live site on the next page load (subject to Google's CSV cache, a few minutes).
- **Crosswalk data changes do need a redeploy**, since that layer is baked into
  the repo: correct the survey CSV, re-run the two scripts, then commit and push.
- The first push of the photos may fail with `HTTP 400 / unexpected disconnect`.
  That is git's 1 MB HTTP post buffer, not a permissions problem. This repo has
  `http.postBuffer` set locally to avoid it; on a fresh clone, run
  `git config http.postBuffer 524288000`.
- **Code changes** (editing `index.html`) just need another `git push` to
  `main` — Pages rebuilds automatically within a minute or so.
- The files the running site needs are `index.html`, `data/crosswalks.json`, and
  `photos/crosswalks/`, and `data/osm_roads.json` is only needed to rebuild. `template.csv` is just a reference/import file for the
  Sheet and isn't read by the site.
- Optional: to use a custom domain (e.g. a `hopewellnj.org` subdomain), add it
  under Settings → Pages → **Custom domain** and create the matching DNS record
  with your domain provider.

## 5. Extending later

- **More crash types**: edit `TYPE_COLOR` / `TYPE_LABEL` near the top of the
  script and add a matching checkbox in the `#controls` markup — filtering,
  legend, and icons follow automatically.
- **Adding the Township back in**: this build is Borough-only, so the
  municipality filter was removed. To cover both towns again, re-add a segmented
  control (buttons with `data-val` values matching the `municipality` column)
  and a filter check in `render()`.
- **Public submission form** (like Mercer County's Vision Zero site): that
  needs an actual intake mechanism, not just a static page. The simplest
  version would be a Google Form that appends to the same Sheet — happy to
  build that out as a second phase if it's useful.
- **Date range filtering, crash count trends over time, heatmap view**: all
  reasonable additions once there's enough real data to make them useful.

## Why not reuse hudcostreets/nj-crashes directly

That project is a much larger statewide pipeline (Python/dashboard stack,
NJDOT bulk data). For a single-town site maintained by a non-technical
volunteer, a static page plus a spreadsheet gets you 90% of the value with
none of the hosting or maintenance overhead. If the township ever wants
county- or state-wide crash trends layered in alongside the local reports,
that repo is the right thing to pull data from at that point.