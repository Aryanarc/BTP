# Indoor Navigation — Demo Web Service

A minimal, working end-to-end skeleton: **upload an [OpenIndoorMaps](https://github.com/openindoormaps/openindoormaps)-style
GeoJSON export → see it rendered floor by floor → submit a free-text query
and get a placeholder acknowledgment back.**

There is **no routing / pathfinding / NLU logic** in this version on purpose.
The `/maps/{id}/query` endpoint just logs whatever you type and returns a
canned response. This is intentional groundwork: the request/response shape
is designed so a real graph-routing engine can be dropped in behind that one
endpoint later without touching the upload pipeline or the frontend.

## Project layout

```
backend/            FastAPI service (upload, retrieve, stub query)
  main.py
  requirements.txt
  storage/          uploaded maps + query logs land here at runtime
frontend/           React + MapLibre GL JS app
  src/
    App.jsx
    components/
      UploadWidget.jsx   file upload -> POST /maps/upload
      MapView.jsx        renders GeoJSON, floor switcher
      QueryBox.jsx        text query -> POST /maps/{id}/query
sample_data/
  sample_map.geojson               our own two-floor toy building (OSM-style tags)
  openindoormaps_caserne.geojson   real OpenIndoorMaps sample export (60 features, 1 floor)
  openindoormaps_demo-map.geojson  real OpenIndoorMaps sample export (411 features, 3 floors)
docker-compose.yml
```

## Running it — Docker (recommended)

```bash
docker compose up --build
```

- Backend: http://localhost:8000 (docs at http://localhost:8000/docs)
- Frontend: http://localhost:5173

## Running it — locally, without Docker

**Backend**
```bash
cd backend
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

**Frontend**
```bash
cd frontend
npm install
npm run dev
```
Vite will print a local URL (default http://localhost:5173).

## Trying the demo

1. Open the frontend in your browser.
2. Upload `sample_data/sample_map.geojson` (or export real data from
   OpenIndoorMaps in the same GeoJSON format — `indoor=room/corridor`,
   `level=*`, `stairs=*`, `highway=elevator`, etc.).
3. The map renders with a floor switcher (Floor 0 / Floor 1 for the sample).
4. Type a query, e.g. *"How do I get from Room A-101 to Lab C-301?"*, and
   submit — you'll get back a "logged, not answered yet" acknowledgment.
   You can also hit `GET /maps/{map_id}/queries` on the backend to see the
   raw log of everything asked so far.

## Using real OpenIndoorMaps data

`sample_data/openindoormaps_demo-map.geojson` and
`openindoormaps_caserne.geojson` are pulled directly from
[openindoormaps/openindoormaps](https://github.com/openindoormaps/openindoormaps)
(`legacy-remix` branch, `public/geojson/`), reused here under its Apache-2.0
license. Upload either one the same way you'd upload the toy sample — no
backend changes are needed, since `/maps/upload` only checks that the file is
a valid GeoJSON `FeatureCollection`, not any particular property schema.

**Their real schema differs from ours**, and it's worth knowing why before you
extend this further:

| | Our `sample_map.geojson` | Real OpenIndoorMaps export |
|---|---|---|
| Floor property | `level` (string, e.g. `"0"`, `"0;1"`) | `level_id` (integer, e.g. `0`, `1`, `2`) |
| Room/POI name | `name` / `ref` | `name`, but **mostly the literal string `"null"`**, not real names |
| Category | `amenity` (`toilets`, `library`, `exit`) | `category` — also mostly null in the sample data |
| Room vs. corridor | `indoor` tag | `feature_type` (`unit` / `corridor` / `unknown`) — inconsistently applied; some `corridor`-tagged features are `MultiLineString`, others are `Polygon` |
| Coordinates | Local, made-up x/y | Real-world lng/lat, georeferenced (the demo building is a real campus) |

The frontend (`MapView.jsx`) now reads **both** shapes: it checks `level` and
`level_id` for floor switching, and normalizes `name`/`ref`/`amenity`/
`category`/`feature_type` into two internal fields (`display_name`,
`style_key`) so styling and labels work either way.

One thing to expect: most rooms in the real sample will render **without a
label**, because OpenIndoorMaps' own release notes admit this pre-alpha data
is placeholder-heavy ("GeoJSON schema design is suboptimal and needs
improvement" — their words, not ours). That's a property of their sample
data, not a bug in this demo — it's actually a good thing to point out in
your review, since it's exactly the kind of real-world messiness a production
ingestion pipeline needs to be robust to (missing names, inconsistent
tagging, mixed geometry types for the same feature type).

## Where to plug in real logic later

Everything lives behind `query_map()` in `backend/main.py`. To add real
routing:
1. On upload, additionally parse the GeoJSON into a graph (rooms/POIs as
   nodes, corridors/doors/stairs/elevators as edges) instead of just storing
   the raw file.
2. Replace the body of `POST /maps/{map_id}/query` with actual parsing of
   `query.text` (or switch the frontend to structured from/to/constraint
   fields) and a Dijkstra/A* search over that graph.
3. Keep the response shape backward-compatible (or version it) so the
   frontend's `QueryBox` component only needs to render richer data, not be
   rewritten.

## Known limitations (by design, for this milestone)

- No authentication, no persistence beyond the local `backend/storage/`
  folder, no map deletion/versioning UI.
- CORS is wide open (`*`) — fine for a local demo, not for deployment.
- The floor switcher assumes a `level` property on features (following OSM
  indoor tagging conventions); maps without it will render as a single
  unfiltered floor.
