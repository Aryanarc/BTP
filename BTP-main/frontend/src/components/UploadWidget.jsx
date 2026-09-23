import { useRef, useState } from "react";
import { API_URL } from "../App.jsx";

export default function UploadWidget({ onUploaded, onError }) {
  const inputRef = useRef(null);
  const [busy, setBusy] = useState(false);

  async function handleFileChange(e) {
    const file = e.target.files?.[0];
    if (!file) return;

    setBusy(true);
    onError(null);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch(`${API_URL}/maps/upload`, {
        method: "POST",
        body: formData,
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        throw new Error(detail.detail || `Upload failed (${res.status})`);
      }
      const info = await res.json();
      onUploaded(info.map_id, info);
    } catch (err) {
      onError(err.message);
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  return (
    <div className="upload-widget">
      <label htmlFor="map-upload" className="upload-label">
        Upload OpenIndoorMaps GeoJSON
      </label>
      <input
        id="map-upload"
        ref={inputRef}
        type="file"
        accept=".geojson,.json,application/geo+json,application/json"
        onChange={handleFileChange}
        disabled={busy}
      />
      {busy && <p className="hint">Uploading…</p>}
    </div>
  );
}
