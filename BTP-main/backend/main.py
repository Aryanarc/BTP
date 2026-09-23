"""
Indoor Navigation Demo — Backend
---------------------------------
Minimal FastAPI service that:
  1. Accepts an OpenIndoorMaps-style GeoJSON upload and stores it.
  2. Serves the stored GeoJSON back for rendering on the frontend map.
  3. Builds a routable graph from that GeoJSON and answers shortest-path
     queries with Dijkstra (Phase 1 of the roadmap — see graph.py).
  4. Accepts free-text "queries" about a map and logs them, returning a
     canned acknowledgment. NLU/Q&A (Phase 2+) is not implemented here yet
     — this endpoint is a placeholder seam for that future work.

On startup, the bundled sample_data/sample_map.geojson is seeded into
storage under a fixed map_id ("sample") if it isn't there yet, so the demo
always has a map to render and route on, even before anything is uploaded.

Run directly with:  uvicorn main:app --reload --host 0.0.0.0 --port 8000
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import networkx as nx
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import graph as routing_graph

STORAGE_DIR = Path(__file__).parent / "storage"
STORAGE_DIR.mkdir(exist_ok=True)

SAMPLE_MAP_ID = "sample"
SAMPLE_MAP_SOURCE = Path(__file__).parent.parent / "sample_data" / "sample_map.geojson"

# In-memory cache of built graphs, keyed by map_id. Rebuilding a graph is
# cheap for demo-sized maps, but there's no reason to redo it on every
# route request, so we cache it the first time a map is touched.
_GRAPH_CACHE: dict[str, nx.Graph] = {}

app = FastAPI(title="Indoor Navigation Demo API")


@app.on_event("startup")
def seed_sample_map() -> None:
    """Ensure a demo map is always present, even before any upload."""
    if _map_path(SAMPLE_MAP_ID).exists() or not SAMPLE_MAP_SOURCE.exists():
        return
    data = json.loads(SAMPLE_MAP_SOURCE.read_text(encoding="utf-8"))
    _map_path(SAMPLE_MAP_ID).write_text(json.dumps(data), encoding="utf-8")

# Wide-open CORS for demo purposes only — tighten this before any real deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class QueryRequest(BaseModel):
    text: str


class QueryResponse(BaseModel):
    status: str
    message: str
    map_id: str
    received_text: str


class RouteRequest(BaseModel):
    from_query: str
    to_query: str


class RouteSegment(BaseModel):
    level: str
    coordinates: list[list[float]]


class RouteResponse(BaseModel):
    map_id: str
    from_name: str
    to_name: str
    distance: float
    levels: list[str]
    segments: list[RouteSegment]
    steps: list[str]


class Poi(BaseModel):
    id: str
    name: str
    ref: str | None = None
    level: str
    kind: str


def _map_path(map_id: str) -> Path:
    return STORAGE_DIR / f"{map_id}.geojson"


def _query_log_path(map_id: str) -> Path:
    return STORAGE_DIR / f"{map_id}_queries.log"


def _get_graph(map_id: str) -> nx.Graph:
    """Return the cached routing graph for a map, building it if needed."""
    if map_id in _GRAPH_CACHE:
        return _GRAPH_CACHE[map_id]
    path = _map_path(map_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Map not found.")
    data = json.loads(path.read_text(encoding="utf-8"))
    g = routing_graph.build_graph(data)
    _GRAPH_CACHE[map_id] = g
    return g


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/maps/upload")
async def upload_map(file: UploadFile = File(...)) -> dict[str, str]:
    """Accept a GeoJSON FeatureCollection (OpenIndoorMaps export format),
    validate it minimally, and store it under a generated map_id."""
    raw = await file.read()

    try:
        data: Any = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"File is not valid JSON: {exc}")

    if not isinstance(data, dict) or data.get("type") != "FeatureCollection":
        raise HTTPException(
            status_code=400,
            detail="Expected a GeoJSON FeatureCollection (top-level 'type' must be "
            "'FeatureCollection').",
        )

    if "features" not in data or not isinstance(data["features"], list):
        raise HTTPException(status_code=400, detail="GeoJSON is missing a 'features' array.")

    map_id = uuid.uuid4().hex[:12]
    _map_path(map_id).write_text(json.dumps(data), encoding="utf-8")
    _GRAPH_CACHE.pop(map_id, None)  # a fresh id never has a stale entry, but be safe

    return {
        "map_id": map_id,
        "feature_count": str(len(data["features"])),
        "filename": file.filename or "unknown",
    }


@app.get("/maps/{map_id}")
def get_map(map_id: str) -> Any:
    """Return the stored GeoJSON as-is, for the frontend to render."""
    path = _map_path(map_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Map not found.")
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/maps/{map_id}/pois", response_model=dict[str, list[Poi]])
def list_pois(map_id: str) -> dict[str, list[Poi]]:
    """Rooms, exits, and tagged POIs that can be used as route endpoints —
    lets the frontend populate "From" / "To" pickers."""
    g = _get_graph(map_id)
    return {"pois": routing_graph.list_routable(g)}


@app.post("/maps/{map_id}/route", response_model=RouteResponse)
def get_route(map_id: str, req: RouteRequest) -> RouteResponse:
    """Phase 1: shortest path between two named rooms/POIs on this map's
    indoor graph, computed with Dijkstra. Handles multi-floor routes via
    the graph's stairs/elevator vertical edges automatically."""
    g = _get_graph(map_id)

    start = routing_graph.find_node(g, req.from_query)
    if start is None:
        raise HTTPException(status_code=404, detail=f"No room/POI matching '{req.from_query}'.")
    end = routing_graph.find_node(g, req.to_query)
    if end is None:
        raise HTTPException(status_code=404, detail=f"No room/POI matching '{req.to_query}'.")
    if start == end:
        raise HTTPException(status_code=400, detail="Start and destination are the same place.")

    try:
        result = routing_graph.shortest_path(g, start, end)
    except nx.NetworkXNoPath as exc:
        raise HTTPException(
            status_code=422,
            detail="No path found between those two points on this map's graph.",
        ) from exc

    return RouteResponse(
        map_id=map_id,
        from_name=g.nodes[start]["name"],
        to_name=g.nodes[end]["name"],
        distance=result["distance"],
        levels=result["levels"],
        segments=result["segments"],
        steps=result["steps"],
    )


@app.post("/maps/{map_id}/query", response_model=QueryResponse)
def query_map(map_id: str, query: QueryRequest) -> QueryResponse:
    """Placeholder query endpoint. Logs the incoming text against the map
    and returns a canned acknowledgment — no answer is computed.

    This is the seam where routing/NLU logic gets plugged in later. The
    request/response shape here is meant to stay stable when that happens.
    """
    if not _map_path(map_id).exists():
        raise HTTPException(status_code=404, detail="Map not found.")

    timestamp = datetime.now(timezone.utc).isoformat()
    with _query_log_path(map_id).open("a", encoding="utf-8") as f:
        f.write(f"{timestamp}\t{query.text}\n")

    return QueryResponse(
        status="received",
        message="Query logged. Routing/answering is not implemented yet.",
        map_id=map_id,
        received_text=query.text,
    )


@app.get("/maps/{map_id}/queries")
def list_queries(map_id: str) -> dict[str, list[str]]:
    """Convenience endpoint so you can see logged queries during the demo."""
    log_path = _query_log_path(map_id)
    if not log_path.exists():
        return {"queries": []}
    lines = log_path.read_text(encoding="utf-8").splitlines()
    return {"queries": lines}
