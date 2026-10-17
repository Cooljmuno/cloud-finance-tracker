import { useAppAuth } from "./auth/AuthContext";
import { LoginPage } from "./features/auth/LoginPage";
import { DashboardPage } from "./features/transactions/DashboardPage";

function App() {
  const auth = useAppAuth();

  if (auth.state === "loading") {
    return (
      <main className="centered-state" aria-live="polite">
        <div className="brand-mark">CF</div>
        <p className="eyebrow">Cloud Finance Tracker</p>
        <h1>Opening your workspace…</h1>
      </main>
    );
  }

  if (auth.state === "error") {
    return (
      <main className="centered-state">
        <div className="brand-mark">CF</div>
        <p className="eyebrow">Service unavailable</p>
        <h1>We could not open the workspace.</h1>
        <p className="muted">{auth.error}</p>
        <button className="primary-button" type="button" onClick={auth.retry}>
          Try again
        </button>
      </main>
    );
  }

  if (auth.state === "anonymous") {
    return <LoginPage />;
  }

  return <DashboardPage />;
}

export default App;
