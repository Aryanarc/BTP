import { useEffect, useState } from "react";
import UploadWidget from "./components/UploadWidget.jsx";
import MapView from "./components/MapView.jsx";
import QueryBox from "./components/QueryBox.jsx";
import RoutePanel from "./components/RoutePanel.jsx";

// Point this at your backend. Defaults to local dev.
export const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

// Fixed id the backend always seeds on startup from sample_data/sample_map.geojson,
// so there's something to look at (and route on) before anyone uploads a file.
const SAMPLE_MAP_ID = "sample";

export default function App() {
  const [mapId, setMapId] = useState(null);
  const [geojson, setGeojson] = useState(null);
  const [uploadInfo, setUploadInfo] = useState(null);
  const [error, setError] = useState(null);
  const [route, setRoute] = useState(null);

  async function handleUploaded(newMapId, info) {
    setError(null);
    setRoute(null);
    setUploadInfo(info);
    setMapId(newMapId);
    try {
      const res = await fetch(`${API_URL}/maps/${newMapId}`);
      if (!res.ok) throw new Error(`Failed to fetch map (${res.status})`);
      const data = await res.json();
      setGeojson(data);
    } catch (err) {
      setError(err.message);
    }
  }

  // No map is present yet -> load the bundled demo map automatically so the
  // upload -> render -> route pipeline is visible immediately.
  useEffect(() => {
    handleUploaded(SAMPLE_MAP_ID, {
      filename: "sample_map.geojson (bundled demo — 2 floors)",
      feature_count: "14",
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="app-shell">
      <header className="app-header">
        <h1>Indoor Navigation — Demo</h1>
        <p className="subtitle">
          Upload an OpenIndoorMaps-style GeoJSON export, view it on the map, and
          find the shortest route between two rooms (Phase 1: graph + Dijkstra
          routing). Natural-language query answering isn't implemented yet.
        </p>
      </header>

      <main className="app-main">
        <aside className="sidebar">
          <UploadWidget onUploaded={handleUploaded} onError={setError} />
          {uploadInfo && (
            <div className="info-box">
              <strong>Map loaded</strong>
              <div>ID: {mapId}</div>
              <div>File: {uploadInfo.filename}</div>
              <div>Features: {uploadInfo.feature_count}</div>
            </div>
          )}
          {error && <div className="error-box">{error}</div>}

          <RoutePanel mapId={mapId} onRoute={setRoute} />
          <QueryBox mapId={mapId} />
        </aside>

        <section className="map-section">
          <MapView geojson={geojson} route={route} />
        </section>
      </main>
    </div>
  );
}
