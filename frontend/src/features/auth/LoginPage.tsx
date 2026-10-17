import { useState, type FormEvent } from "react";

import { useAppAuth } from "../../auth/AuthContext";

export function LoginPage() {
  const { mode, signIn } = useAppAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await signIn(mode === "session" ? { username, password } : undefined);
    } catch (requestError: unknown) {
      setError(requestError instanceof Error ? requestError.message : "Sign-in failed.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="login-shell">
      <section className="login-story" aria-labelledby="login-heading">
        <div className="brand-mark" aria-hidden="true">
          CF
        </div>
        <p className="eyebrow">Cloud Finance Tracker</p>
        <h1 id="login-heading">A clearer view of every transaction.</h1>
        <p className="login-copy">
          A production-shaped portfolio app for secure financial workflows, built with Django,
          React, PostgreSQL, and AWS-ready authentication.
        </p>
        <div className="security-note">
          <span aria-hidden="true">◆</span>
          <p>
            This demonstration uses synthetic data only. Production sign-in uses OAuth 2.0 and
            OpenID Connect through Amazon Cognito.
          </p>
        </div>
      </section>

      <section className="login-card" aria-label="Sign in">
        <p className="card-kicker">Portfolio workspace</p>
        <h2>Welcome back</h2>
        <p className="muted">
          {mode === "session"
            ? "Use the local demo account created by the setup command."
            : "Continue to the secure Cognito-hosted sign-in page."}
        </p>

        <form onSubmit={handleSubmit}>
          {mode === "session" ? (
            <>
              <label htmlFor="username">Username</label>
              <input
                id="username"
                name="username"
                autoComplete="username"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                required
              />
              <label htmlFor="password">Password</label>
              <input
                id="password"
                name="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
              />
            </>
          ) : null}

          {error ? (
            <p className="form-error" role="alert">
              {error}
            </p>
          ) : null}

          <button className="primary-button login-button" type="submit" disabled={submitting}>
            {submitting ? "Signing in…" : mode === "session" ? "Sign in" : "Continue with Cognito"}
          </button>
        </form>
        <p className="auth-mode">{mode === "session" ? "Local session + CSRF" : "OAuth 2.0 + PKCE"}</p>
      </section>
    </main>
  );
}
