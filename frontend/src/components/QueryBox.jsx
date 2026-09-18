import { useState } from "react";
import { API_URL } from "../App.jsx";

export default function QueryBox({ mapId }) {
  const [text, setText] = useState("");
  const [response, setResponse] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!mapId || !text.trim()) return;

    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`${API_URL}/maps/${mapId}/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      if (!res.ok) throw new Error(`Query failed (${res.status})`);
      const data = await res.json();
      setResponse(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  const disabled = !mapId;

  return (
    <form className="query-box" onSubmit={handleSubmit}>
      <label htmlFor="query-input" className="upload-label">
        Ask about the map
      </label>
      <textarea
        id="query-input"
        rows={3}
        placeholder={
          disabled
            ? "Upload a map first…"
            : "e.g. How do I get from Room A-101 to Lab C-301?"
        }
        value={text}
        onChange={(e) => setText(e.target.value)}
        disabled={disabled || busy}
      />
      <button type="submit" disabled={disabled || busy || !text.trim()}>
        {busy ? "Sending…" : "Submit query"}
      </button>

      {error && <div className="error-box">{error}</div>}

      {response && (
        <div className="response-box">
          <strong>Response</strong>
          <div>{response.message}</div>
          <div className="hint">(No route/answer is computed yet — this only confirms the round trip.)</div>
        </div>
      )}
    </form>
  );
}
