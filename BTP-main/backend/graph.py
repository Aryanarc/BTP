"""
graph.py — Phase 1: Graph + Routing
------------------------------------
Turns an OpenIndoorMaps / OSM-indoor style GeoJSON FeatureCollection into a
weighted, routable graph, and finds shortest paths across it with Dijkstra
(via networkx). This is the piece the roadmap calls "build the indoor graph
from existing GeoJSON; implement Dijkstra/A*; render the route on the map".

Node model
----------
- Corridor LineString/MultiLineString vertices become the walkable backbone.
  Consecutive vertices are connected with an edge weighted by straight-line
  distance.
- Each room (Polygon/MultiPolygon) becomes one node at its centroid, snapped
  to the nearest corridor vertex on the same floor.
- Point features (stairs, elevators, exits, other tagged POIs) become nodes
  at their coordinates, also snapped to the nearest corridor vertex on each
  floor they belong to.
- A stairway or elevator whose `level` (or `level_id`) lists more than one
  floor (OSM-style "0;1") becomes one node per floor, linked by a vertical
  edge with a fixed cost — this is how multi-floor routing falls out of the
  same graph without special-casing floor changes anywhere else.

Coordinates are treated as a flat, local plane (as OpenIndoorMaps/CAD-style
indoor exports typically are), so edge weights are plain Euclidean distance.
"""

from __future__ import annotations

import math
from typing import Any, Optional

import networkx as nx

# Fixed costs for crossing a floor. Tuned so the router prefers an elevator
# over stairs when both are available, matching the "physical distance by
# default" model from the roadmap (accessibility-aware weighting is Phase 3).
STAIR_VERTICAL_COST = 15.0
ELEVATOR_VERTICAL_COST = 8.0


def _levels_of(props: dict) -> list[str]:
    """Read `level` (OSM-style, possibly ';'-separated) or `level_id`."""
    raw = props.get("level")
    if raw is None:
        raw = props.get("level_id")
    if raw is None or raw == "null":
        return ["0"]
    return [p.strip() for p in str(raw).split(";") if p.strip()]


def _centroid(coords: Any) -> tuple[float, float]:
    """Average-of-vertices centroid of a Polygon/MultiPolygon coordinate
    array. Good enough as a routing anchor point for room shapes."""
    pts: list[list[float]] = []

    def visit(c: Any) -> None:
        if isinstance(c[0], (int, float)):
            pts.append(c)
        else:
            for sub in c:
                visit(sub)

    visit(coords)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (sum(xs) / len(xs), sum(ys) / len(ys))


def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _classify(props: dict) -> str:
    """Map a feature's tags onto one of our node kinds."""
    if "stairs" in props:
        return "stairs"
    if props.get("highway") == "elevator":
        return "elevator"
    if props.get("amenity") == "exit":
        return "exit"
    indoor = props.get("indoor")
    feature_type = props.get("feature_type")
    if indoor == "room" or feature_type == "unit":
        return "room"
    if indoor == "corridor" or feature_type == "corridor":
        return "corridor"
    return "poi"


def _display_name(props: dict) -> str:
    return props.get("name") or props.get("ref") or props.get("alt_name") or "Unnamed"


def build_graph(geojson: dict) -> nx.Graph:
    """Build the routable graph for one map's GeoJSON FeatureCollection."""
    g = nx.Graph()
    corridor_nodes_by_level: dict[str, list[str]] = {}
    # (kind, rounded-x, rounded-y) -> node ids for that same physical point
    # across floors, so stairs/elevators can be linked vertically.
    vertical_groups: dict[tuple[str, float, float], list[str]] = {}

    features = geojson.get("features", [])

    # Pass 1 — corridors become the walkable backbone.
    for i, feat in enumerate(features):
        props = feat.get("properties") or {}
        geom = feat.get("geometry") or {}
        if _classify(props) != "corridor":
            continue
        gtype = geom.get("type")
        coords = geom.get("coordinates")
        if gtype == "LineString":
            lines = [coords]
        elif gtype == "MultiLineString":
            lines = coords
        else:
            continue
        for level in _levels_of(props):
            for line in lines:
                prev_id = None
                for j, pt in enumerate(line):
                    node_id = f"c{i}-{j}:{level}"
                    g.add_node(
                        node_id, x=pt[0], y=pt[1], level=level,
                        kind="corridor", name="Corridor", routable=False,
                    )
                    corridor_nodes_by_level.setdefault(level, []).append(node_id)
                    if prev_id is not None:
                        p = (g.nodes[prev_id]["x"], g.nodes[prev_id]["y"])
                        g.add_edge(prev_id, node_id, weight=_dist(p, pt), kind="corridor")
                    prev_id = node_id

    def nearest_corridor(level: str, xy: tuple[float, float]) -> Optional[str]:
        candidates = corridor_nodes_by_level.get(level, [])
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda nid: _dist((g.nodes[nid]["x"], g.nodes[nid]["y"]), xy),
        )

    # Pass 2 — rooms and point features (stairs, elevators, exits, POIs).
    for i, feat in enumerate(features):
        props = feat.get("properties") or {}
        geom = feat.get("geometry") or {}
        kind = _classify(props)
        if kind == "corridor":
            continue

        gtype = geom.get("type")
        name = _display_name(props)
        ref = props.get("ref")

        if kind == "room":
            if gtype not in ("Polygon", "MultiPolygon") or not geom.get("coordinates"):
                continue
            xy = _centroid(geom["coordinates"])
            for level in _levels_of(props):
                node_id = f"r{i}:{level}"
                g.add_node(
                    node_id, x=xy[0], y=xy[1], level=level, kind="room",
                    name=name, ref=ref, routable=True,
                )
                nearest = nearest_corridor(level, xy)
                if nearest:
                    npt = (g.nodes[nearest]["x"], g.nodes[nearest]["y"])
                    g.add_edge(node_id, nearest, weight=_dist(xy, npt), kind="access")
            continue

        if gtype != "Point" or not geom.get("coordinates"):
            continue
        xy = tuple(geom["coordinates"])
        levels = _levels_of(props)
        group_key = (kind, round(xy[0], 3), round(xy[1], 3))
        level_node_ids = []
        for level in levels:
            node_id = f"p{i}:{level}"
            routable = kind in ("exit", "poi")
            g.add_node(
                node_id, x=xy[0], y=xy[1], level=level, kind=kind,
                name=name, ref=ref, routable=routable,
            )
            nearest = nearest_corridor(level, xy)
            if nearest:
                npt = (g.nodes[nearest]["x"], g.nodes[nearest]["y"])
                g.add_edge(node_id, nearest, weight=_dist(xy, npt), kind="access")
            level_node_ids.append(node_id)
        if kind in ("stairs", "elevator") and len(level_node_ids) > 1:
            vertical_groups.setdefault(group_key, []).extend(level_node_ids)

    # Pass 3 — vertical edges: the same stairwell/elevator, one node per
    # floor it touches, linked pairwise with a fixed floor-crossing cost.
    for (kind, _, _), node_ids in vertical_groups.items():
        cost = STAIR_VERTICAL_COST if kind == "stairs" else ELEVATOR_VERTICAL_COST
        for a in range(len(node_ids)):
            for b in range(a + 1, len(node_ids)):
                g.add_edge(node_ids[a], node_ids[b], weight=cost, kind=kind)

    return g


def list_routable(g: nx.Graph) -> list[dict]:
    """Rooms, exits and tagged POIs a user can route to/from."""
    out = []
    for nid, data in g.nodes(data=True):
        if data.get("routable"):
            out.append({
                "id": nid,
                "name": data["name"],
                "ref": data.get("ref"),
                "level": data["level"],
                "kind": data["kind"],
            })
    out.sort(key=lambda p: (p["level"], p["name"]))
    return out


def find_node(g: nx.Graph, query: str) -> Optional[str]:
    """Best-effort lookup of a routable node by ref or name.

    Exact (case-insensitive) matches on `ref` or `name` win outright;
    otherwise the first substring match is used.
    """
    if not query:
        return None
    q = query.strip().lower()
    best = None
    for nid, data in g.nodes(data=True):
        if not data.get("routable"):
            continue
        ref = (data.get("ref") or "").lower()
        name = (data.get("name") or "").lower()
        if q == ref or q == name:
            return nid
        if best is None and q and (q in ref or q in name):
            best = nid
    return best


def shortest_path(g: nx.Graph, start: str, end: str) -> dict:
    """Dijkstra shortest path between two node ids, shaped for the API/UI:
    per-floor line segments (for rendering) plus a plain-English step list.
    """
    path = nx.dijkstra_path(g, start, end, weight="weight")
    length = nx.dijkstra_path_length(g, start, end, weight="weight")

    coords_by_level: dict[str, list[list[float]]] = {}
    steps: list[str] = []
    prev_level = None

    for idx, nid in enumerate(path):
        data = g.nodes[nid]
        level = data["level"]
        coords_by_level.setdefault(level, []).append([data["x"], data["y"]])

        if idx == 0:
            steps.append(f"Start at {data['name']} (floor {level}).")
        elif idx == len(path) - 1:
            steps.append(f"Arrive at {data['name']} (floor {level}).")
        elif prev_level is not None and level != prev_level and data["kind"] in ("stairs", "elevator"):
            via = "the stairs" if data["kind"] == "stairs" else "the elevator"
            steps.append(f"Take {via} to floor {level}.")
        prev_level = level

    def _level_key(lvl: str) -> float:
        try:
            return float(lvl)
        except ValueError:
            return 0.0

    return {
        "distance": round(length, 2),
        "levels": sorted(coords_by_level.keys(), key=_level_key),
        "segments": [{"level": lvl, "coordinates": pts} for lvl, pts in coords_by_level.items()],
        "steps": steps,
        "node_count": len(path),
    }
