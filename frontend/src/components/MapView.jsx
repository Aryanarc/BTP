import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

const SOURCE_ID = "indoor-data";

// Blank style — this is an indoor plan, not a georeferenced basemap, so we
// just give MapLibre a flat background to draw the floor plan on.
const BLANK_STYLE = {
  version: 8,
  sources: {},
  layers: [{ id: "background", type: "background", paint: { "background-color": "#f4f5f7" } }],
};

// Different indoor-map sources use different property names for "which floor
// is this on". Our own sample data uses `level` (OSM-style, e.g. "0" or a
// ";"-separated "0;1" for a shared stairwell). Real OpenIndoorMaps exports
// use `level_id` (a plain integer per floor, e.g. 0, 1, 2) instead. We read
// both so either kind of upload works without the user editing the file.
function levelValuesOf(props) {
  if (!props) return [];
  const raw = props.level ?? props.level_id;
  if (raw === undefined || raw === null || raw === "null") return [];
  return String(raw)
    .split(";")
    .map((s) => s.trim())
    .filter(Boolean);
}

function extractLevels(geojson) {
  const levels = new Set();
  for (const f of geojson.features || []) {
    levelValuesOf(f.properties).forEach((lvl) => levels.add(lvl));
  }
  return Array.from(levels).sort((a, b) => Number(a) - Number(b));
}

// Real OpenIndoorMaps exports currently ship a lot of placeholder data: the
// literal string "null" instead of a JSON null, and a separate `feature_type`
// (corridor/unit/unknown) instead of our own `amenity`/`ref` fields. This
// normalizes both shapes into a couple of predictable properties
// (`display_name`, `style_key`) so the render logic below doesn't need to
// special-case every upstream source.
function sanitizeGeojson(geojson) {
  const features = (geojson.features || []).map((f) => {
    const props = { ...(f.properties || {}) };
    for (const key of Object.keys(props)) {
      if (props[key] === "null") props[key] = null;
    }
    const displayName = props.name || props.ref || props.alt_name || null;
    const styleKey = props.amenity || props.category || props.feature_type || null;
    return { ...f, properties: { ...props, display_name: displayName, style_key: styleKey } };
  });
  return { ...geojson, features };
}

function boundsOf(geojson) {
  const bounds = new maplibregl.LngLatBounds();
  let any = false;
  const visit = (coords) => {
    if (typeof coords[0] === "number") {
      bounds.extend(coords);
      any = true;
    } else {
      coords.forEach(visit);
    }
  };
  for (const f of geojson.features || []) {
    if (f.geometry?.coordinates) visit(f.geometry.coordinates);
  }
  return any ? bounds : null;
}

export default function MapView({ geojson }) {
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const [levels, setLevels] = useState([]);
  const [activeLevel, setActiveLevel] = useState(null);

  // Initialize map once.
  useEffect(() => {
    if (mapRef.current || !containerRef.current) return;
    mapRef.current = new maplibregl.Map({
      container: containerRef.current,
      style: BLANK_STYLE,
      center: [0, 0],
      zoom: 2,
    });
    mapRef.current.addControl(new maplibregl.NavigationControl(), "top-right");
  }, []);

  // Load / replace data whenever a new map is uploaded.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !geojson) return;

    const data = sanitizeGeojson(geojson);
    const detectedLevels = extractLevels(data);
    setLevels(detectedLevels);
    const initialLevel = detectedLevels[0] ?? null;
    setActiveLevel(initialLevel);

    const apply = () => {
      if (map.getLayer("rooms-fill")) map.removeLayer("rooms-fill");
      if (map.getLayer("rooms-outline")) map.removeLayer("rooms-outline");
      if (map.getLayer("corridors-line")) map.removeLayer("corridors-line");
      if (map.getLayer("poi-points")) map.removeLayer("poi-points");
      if (map.getLayer("poi-labels")) map.removeLayer("poi-labels");
      if (map.getSource(SOURCE_ID)) map.removeSource(SOURCE_ID);

      map.addSource(SOURCE_ID, { type: "geojson", data });

      // Polygons: rooms, units, and (in some exports) even corridors.
      map.addLayer({
        id: "rooms-fill",
        type: "fill",
        source: SOURCE_ID,
        filter: ["any", ["==", ["geometry-type"], "Polygon"], ["==", ["geometry-type"], "MultiPolygon"]],
        paint: {
          "fill-color": [
            "match",
            ["get", "style_key"],
            "toilets", "#cde4ff",
            "library", "#ffe6b3",
            "exit", "#ffd0d0",
            "corridor", "#e4e4e4",
            "unit", "#dbe8dc",
            "#dbe8dc",
          ],
          "fill-opacity": 0.85,
        },
      });

      map.addLayer({
        id: "rooms-outline",
        type: "line",
        source: SOURCE_ID,
        filter: ["any", ["==", ["geometry-type"], "Polygon"], ["==", ["geometry-type"], "MultiPolygon"]],
        paint: { "line-color": "#4a4a4a", "line-width": 1 },
      });

      // Lines: corridors/walls. Real OpenIndoorMaps exports mostly use
      // MultiLineString here rather than a plain LineString.
      map.addLayer({
        id: "corridors-line",
        type: "line",
        source: SOURCE_ID,
        filter: ["any", ["==", ["geometry-type"], "LineString"], ["==", ["geometry-type"], "MultiLineString"]],
        paint: { "line-color": "#9a9a9a", "line-width": 3, "line-dasharray": [2, 1] },
      });

      map.addLayer({
        id: "poi-points",
        type: "circle",
        source: SOURCE_ID,
        filter: ["==", ["geometry-type"], "Point"],
        paint: {
          "circle-radius": 6,
          "circle-color": [
            "case",
            ["has", "stairs"], "#e07b39",
            ["==", ["get", "highway"], "elevator"], "#3f7ce0",
            ["==", ["get", "style_key"], "exit"], "#d64545",
            "#555555",
          ],
          "circle-stroke-width": 1,
          "circle-stroke-color": "#ffffff",
        },
      });

      map.addLayer({
        id: "poi-labels",
        type: "symbol",
        source: SOURCE_ID,
        layout: {
          "text-field": ["coalesce", ["get", "display_name"], ""],
          "text-size": 11,
          "text-offset": [0, 1.1],
          "text-anchor": "top",
        },
        paint: { "text-color": "#222222", "text-halo-color": "#ffffff", "text-halo-width": 1 },
      });

      if (initialLevel !== null) applyLevelFilter(map, initialLevel);

      const b = boundsOf(data);
      if (b) map.fitBounds(b, { padding: 40, duration: 0 });
    };

    if (map.isStyleLoaded()) apply();
    else map.once("load", apply);
  }, [geojson]);

  // Re-filter layers when the active floor changes.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || activeLevel === null) return;
    if (map.getSource(SOURCE_ID)) applyLevelFilter(map, activeLevel);
  }, [activeLevel]);

  function applyLevelFilter(map, level) {
    // A feature belongs to this floor if either `level` or `level_id`
    // (whichever the source data uses) matches — possibly ";"-separated,
    // e.g. "0;1" for a shared stairwell/elevator.
    const matchesLevel = (prop) => [
      "any",
      ["==", ["to-string", ["get", prop]], level],
      ["in", level, ["to-string", ["get", prop]]],
    ];
    const levelFilter = ["any", matchesLevel("level"), matchesLevel("level_id")];

    const baseFilters = {
      "rooms-fill": ["any", ["==", ["geometry-type"], "Polygon"], ["==", ["geometry-type"], "MultiPolygon"]],
      "rooms-outline": ["any", ["==", ["geometry-type"], "Polygon"], ["==", ["geometry-type"], "MultiPolygon"]],
      "corridors-line": ["any", ["==", ["geometry-type"], "LineString"], ["==", ["geometry-type"], "MultiLineString"]],
      "poi-points": ["==", ["geometry-type"], "Point"],
      "poi-labels": ["==", ["geometry-type"], "Point"],
    };
    Object.entries(baseFilters).forEach(([layerId, baseFilter]) => {
      map.setFilter(layerId, ["all", baseFilter, levelFilter]);
    });
  }

  return (
    <div className="map-view">
      {levels.length > 1 && (
        <div className="floor-switcher">
          {levels.map((lvl) => (
            <button
              key={lvl}
              className={lvl === activeLevel ? "active" : ""}
              onClick={() => setActiveLevel(lvl)}
            >
              Floor {lvl}
            </button>
          ))}
        </div>
      )}
      <div ref={containerRef} className="map-container" />
      {!geojson && <div className="map-placeholder">Upload a map to see it here.</div>}
    </div>
  );
}
