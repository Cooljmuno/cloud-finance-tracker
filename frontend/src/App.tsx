import { useEffect, useState } from "react";

import { getHealthStatus } from "./api/health";

type ConnectionState = "checking" | "connected" | "unavailable";

function App() {
  const [connectionState, setConnectionState] = useState<ConnectionState>("checking");

  useEffect(() => {
    const controller = new AbortController();

    getHealthStatus(controller.signal)
      .then(() => setConnectionState("connected"))
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setConnectionState("unavailable");
      });

    return () => controller.abort();
  }, []);

  const statusCopy = {
    checking: {
      label: "Checking services",
      description: "Contacting the Django API and PostgreSQL database.",
    },
    connected: {
      label: "API connected",
      description: "Django responded and confirmed its database connection.",
    },
    unavailable: {
      label: "Connection unavailable",
      description: "Start the local services and retry this page.",
    },
  }[connectionState];

  return (
    <main className="app-shell">
      <section className="intro" aria-labelledby="page-title">
        <p className="eyebrow">Cloud Finance Tracker</p>
        <h1 id="page-title">Your money, organized around clear decisions.</h1>
        <p className="intro-copy">
          Import transactions, apply transparent categorization rules, set monthly budgets, and
          understand where your money goes.
        </p>
      </section>

      <section className="foundation-card" aria-live="polite">
        <div>
          <p className="card-label">Foundation status</p>
          <h2>{statusCopy.label}</h2>
          <p>{statusCopy.description}</p>
        </div>
        <span className={`status-dot status-dot--${connectionState}`} aria-hidden="true" />
      </section>

      <section className="feature-grid" aria-label="Planned finance tracker capabilities">
        <article>
          <span>01</span>
          <h2>Transactions</h2>
          <p>Import consistent, validated records without using real banking data.</p>
        </article>
        <article>
          <span>02</span>
          <h2>Rules</h2>
          <p>Apply deterministic categories that remain explainable and editable.</p>
        </article>
        <article>
          <span>03</span>
          <h2>Budgets</h2>
          <p>Compare monthly spending against limits calculated by the backend.</p>
        </article>
      </section>
    </main>
  );
}

export default App;

