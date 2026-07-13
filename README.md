# Hopewell Area Crash Map — Setup Guide

A single-file replacement for the Google My Maps crash map, built with Leaflet.
No server, no database — the "backend" is a Google Sheet, so anyone comfortable
with spreadsheets can maintain the data with no code involved.

Open `index.html` in a browser and it reads live from the published Google
Sheet — that Sheet is the site's single source of truth. No crash data is baked
into the HTML; if the Sheet can't be reached, the map shows a visible "data
unavailable" state rather than stale data. Everything below is about
maintaining the data in the Sheet.

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
   | `municipality` | yes | Exactly `Hopewell Borough` or `Hopewell Township` (case-sensitive, used for the filter) |
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

## 3. Deploying

It's one HTML file with no build step, so any static host works:

- **Render**: New → Static Site → point it at a GitHub repo containing this
  file (root `index.html`) → deploy. No build command needed; leave the
  publish directory as `.`
- **Netlify or Vercel**: drag-and-drop this folder onto their dashboard —
  even faster than Render for something this simple.
- **GitHub Pages**: push this folder to a repo, enable Pages in the repo
  settings, pick the branch/root.

Whichever you pick, the only file that matters is `index.html` — the CSV
template is just for setting up the Sheet and isn't read by the site itself.

## 4. Extending later

- **More crash types or municipalities**: edit the `TYPE_COLOR` / `TYPE_LABEL`
  and the municipality buttons (`#muniSeg`) near the top of the script and
  markup — everything else (filtering, legend, icons) follows automatically
  for the four existing types, and the municipality filter is driven by
  whatever string is in the `municipality` column.
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