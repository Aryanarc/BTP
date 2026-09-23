# Indoor Navigation — Demo Web Service

**Phase 1 of the roadmap (Graph + Routing) is implemented.** Upload an
[OpenIndoorMaps](https://github.com/openindoormaps/openindoormaps)-style
GeoJSON export → it's rendered floor by floor → pick a "From" and "To" room
and get the shortest walking route back, computed with Dijkstra over a graph
built from the map, crossing floors via stairs/elevators automatically. A
demo two-floor map is bundled and loads automatically, so there's something
to route on immediately, with no upload required.

Free-text natural-language Q&A (`/maps/{id}/query`) is still a placeholder —
that's Phase 2+ on the roadmap, not built yet (see "Roadmap status" below).

## Project layout

```
backend/
  main.py            FastAPI service: upload, retrieve, graph-backed
                      /pois and /route endpoints, stub /query
  graph.py            Phase 1: builds the routable graph from GeoJSON and
                      runs Dijkstra shortest-path over it
  requirements.txt
  storage/            uploaded maps + query logs land here at runtime;
                      "sample.geojson" is auto-seeded on startup
frontend/            React + MapLibre GL JS app
  src/
    App.jsx
    components/
      UploadWidget.jsx   file upload -> POST /maps/upload
      MapView.jsx        renders GeoJSON, floor switcher, route overlay
      RoutePanel.jsx     From/To pickers -> POST /maps/{id}/route
      QueryBox.jsx       text query -> POST /maps/{id}/query (placeholder)
sample_data/
  sample_map.geojson               our own two-floor toy building (OSM-style tags) — auto-loaded as the demo map
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

1. Open the frontend in your browser. The bundled two-floor sample map loads
   automatically (backend seeds it as map id `sample` on startup) — no
   upload needed to try routing.
2. In **Find a route**, pick a "From" and "To" room/POI (e.g. `Room A-101` →
   `Lab C-301`) and click **Get route**. The path is drawn on the map and the
   step list explains it, e.g. *"Take the elevator to floor 1."* Switch the
   floor switcher to Floor 1 to see the rest of the route.
3. To try a different building, upload your own `sample_data/*.geojson` (or
   export real data from OpenIndoorMaps — `indoor=room/corridor`, `level=*`,
   `stairs=*`, `highway=elevator`, etc.) with the **Upload** widget; the
   route picker repopulates from the new map's graph.
4. The **Ask about the map** box still just logs free text and returns a
   placeholder acknowledgment — natural-language Q&A is Phase 2, not built
   yet. You can hit `GET /maps/{map_id}/queries` on the backend to see the
   raw log of everything asked so far.

## Routing API

- `GET /maps/{map_id}/pois` — rooms/exits/POIs that can be used as route
  endpoints: `{"pois": [{"id", "name", "ref", "level", "kind"}, ...]}`.
- `POST /maps/{map_id}/route` — body `{"from_query": "A-101", "to_query": "C-301"}`
  (matches by `ref` or `name`, case-insensitive, exact match preferred, then
  substring). Returns distance, the floors crossed, one line-segment per
  floor (for rendering), and a plain-English step list.

Try it directly: `POST http://localhost:8000/maps/sample/route` with the
body above, or use the interactive docs at `/docs`.

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

## How the graph + routing works (`backend/graph.py`)

- **Nodes**: every corridor `LineString`/`MultiLineString` vertex becomes a
  backbone node; every room polygon becomes one node at its centroid; every
  stairs/elevator/exit/POI point becomes a node. Rooms and POIs snap to the
  nearest corridor node on their own floor.
- **Edges**: consecutive corridor vertices are connected, weighted by
  straight-line distance; each room/POI gets one "access" edge to its
  nearest corridor node.
- **Multi-floor**: a stairs or elevator feature whose `level` lists more than
  one floor (OSM-style `"0;1"`) becomes one node per floor, linked by a
  fixed-cost vertical edge (elevators cost less than stairs, so the router
  prefers them when both exist) — no floor-change special-casing needed
  anywhere else.
- **Search**: `networkx.dijkstra_path` over that graph. Swapping in A* later
  (roadmap mentions both) is a one-line change since node coordinates are
  already on every node for a heuristic.
- Coordinates are treated as a flat local plane, matching `sample_map.geojson`
  and typical indoor/CAD-style exports. Real-world lng/lat data (like the
  bundled OpenIndoorMaps samples) will still build a graph and route, but
  edge weights would need a haversine distance instead of Euclidean for the
  numbers to mean real metres — worth fixing if you route on that data.

## Roadmap status

| Phase | Scope | Status |
|---|---|---|
| **1** | Graph + routing (this update) | ✅ Done — `graph.py`, `/pois`, `/route`, route overlay + picker in the UI |
| 2 | Rule-based Q&A wired into `/query` | Not started — `/query` is still the original placeholder |
| 3 | Accessibility-aware routing, POI search, nearest-feature queries | Not started — `graph.py`'s edge weights are a natural place to add an `avoid_stairs` / `fewest_transitions` mode |
| 4 | RAG for open-ended Q&A, floor-plan-image extraction, voice/AR | Not started — stretch goals per the roadmap |

## Known limitations (by design, for this milestone)

- No authentication, no persistence beyond the local `backend/storage/`
  folder, no map deletion/versioning UI.
- CORS is wide open (`*`) — fine for a local demo, not for deployment.
- The floor switcher assumes a `level` property on features (following OSM
  indoor tagging conventions); maps without it will render as a single
  unfiltered floor.
- Routing only considers physical distance (Phase 1 scope). No accessibility
  modes, POI/semantic search, or safety/evacuation routing yet — all flagged
  as later phases above.
- The graph has no notion of doors as separate crossing points yet (rooms
  connect straight to the corridor backbone); fine for the sample data's
  granularity, worth revisiting for denser real floor plans.
