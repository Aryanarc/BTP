import { useState } from "react";
import UploadWidget from "./components/UploadWidget.jsx";
import MapView from "./components/MapView.jsx";
import QueryBox from "./components/QueryBox.jsx";

// Point this at your backend. Defaults to local dev.
export const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export default function App() {
  const [mapId, setMapId] = useState(null);
  const [geojson, setGeojson] = useState(null);
  const [uploadInfo, setUploadInfo] = useState(null);
  const [error, setError] = useState(null);

  async function handleUploaded(newMapId, info) {
    setError(null);
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

  return (
    <div className="app-shell">
      <header className="app-header">
        <h1>Indoor Navigation — Demo</h1>
        <p className="subtitle">
          Upload an OpenIndoorMaps-style GeoJSON export, view it on the map, and
          submit a query. Query answering isn't implemented yet — this demo proves
          the upload → render → ask pipeline.
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
          <QueryBox mapId={mapId} />
        </aside>

        <section className="map-section">
          <MapView geojson={geojson} />
        </section>
      </main>
    </div>
  );
}
