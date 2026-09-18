"""
Indoor Navigation Demo — Backend
---------------------------------
Minimal FastAPI service that:
  1. Accepts an OpenIndoorMaps-style GeoJSON upload and stores it.
  2. Serves the stored GeoJSON back for rendering on the frontend map.
  3. Accepts free-text "queries" about a map and logs them, returning a
     canned acknowledgment. NO routing / NLU / pathfinding logic lives here
     yet — this endpoint is a placeholder seam for that future work.

Run directly with:  uvicorn main:app --reload --host 0.0.0.0 --port 8000
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

STORAGE_DIR = Path(__file__).parent / "storage"
STORAGE_DIR.mkdir(exist_ok=True)

app = FastAPI(title="Indoor Navigation Demo API")

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


def _map_path(map_id: str) -> Path:
    return STORAGE_DIR / f"{map_id}.geojson"


def _query_log_path(map_id: str) -> Path:
    return STORAGE_DIR / f"{map_id}_queries.log"


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
