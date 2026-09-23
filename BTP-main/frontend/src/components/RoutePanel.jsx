import { useEffect, useState } from "react";
import { API_URL } from "../App.jsx";

// Phase 1: Graph + Routing. Lets the user pick a "From" / "To" room or POI
// (populated from the map's graph) and fetches the shortest path from the
// backend's /route endpoint (Dijkstra over the indoor graph).
export default function RoutePanel({ mapId, onRoute }) {
  const [pois, setPois] = useState([]);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  // Reload the pickable rooms/POIs whenever the active map changes.
  useEffect(() => {
    setPois([]);
    setFrom("");
    setTo("");
    setResult(null);
    setError(null);
    onRoute(null);
    if (!mapId) return;

    let cancelled = false;
    fetch(`${API_URL}/maps/${mapId}/pois`)
      .then((res) => res.json())
      .then((data) => {
        if (!cancelled) setPois(data.pois || []);
      })
      .catch(() => {
        if (!cancelled) setPois([]);
      });
    return () => {
      cancelled = true;
    };
  }, [mapId]);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!mapId || !from || !to) return;

    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const res = await fetch(`${API_URL}/maps/${mapId}/route`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ from_query: from, to_query: to }),
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        throw new Error(detail.detail || `Route failed (${res.status})`);
      }
      const data = await res.json();
      setResult(data);
      onRoute(data);
    } catch (err) {
      setError(err.message);
      onRoute(null);
    } finally {
      setBusy(false);
    }
  }

  const disabled = !mapId || pois.length === 0;

  return (
    <form className="route-panel" onSubmit={handleSubmit}>
      <label className="upload-label">Find a route</label>

      <select value={from} onChange={(e) => setFrom(e.target.value)} disabled={disabled}>
        <option value="">From…</option>
        {pois.map((p) => (
          <option key={p.id} value={p.ref || p.name}>
            {p.name} (floor {p.level})
          </option>
        ))}
      </select>

      <select value={to} onChange={(e) => setTo(e.target.value)} disabled={disabled}>
        <option value="">To…</option>
        {pois.map((p) => (
          <option key={p.id} value={p.ref || p.name}>
            {p.name} (floor {p.level})
          </option>
        ))}
      </select>

      <button type="submit" disabled={disabled || busy || !from || !to}>
        {busy ? "Routing…" : "Get route"}
      </button>

      {disabled && mapId && (
        <p className="hint">This map has no rooms or POIs tagged for routing yet.</p>
      )}
      {error && <div className="error-box">{error}</div>}

      {result && (
        <div className="response-box">
          <strong>
            {result.from_name} → {result.to_name}
          </strong>
          <div>
            {result.distance} units · {result.steps.length} step
            {result.steps.length === 1 ? "" : "s"}
            {result.levels.length > 1 ? ` · crosses ${result.levels.length} floors` : ""}
          </div>
          <ol className="route-steps">
            {result.steps.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ol>
        </div>
      )}
    </form>
  );
}
