import { useEffect, useState } from "react";

interface Health {
  status: string;
  version: string;
  environment: string;
}

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/healthcheck")
      .then((r) => r.json())
      .then((data: Health) => setHealth(data))
      .catch((e: unknown) => setError(String(e)));
  }, []);

  return (
    <main style={{ fontFamily: "system-ui, sans-serif", padding: "2rem" }}>
      <h1>OSINT Knowledge Graph</h1>
      <p>Entity tracker &amp; interactive knowledge graph (Phase 1 scaffold).</p>
      <section>
        <h2>Backend status</h2>
        {error && <p style={{ color: "crimson" }}>API unreachable: {error}</p>}
        {health ? (
          <pre>{JSON.stringify(health, null, 2)}</pre>
        ) : (
          !error && <p>Loading…</p>
        )}
      </section>
    </main>
  );
}
