# ADR 0004: Use sessions locally and Cognito in production

- Status: Accepted
- Date: 2026-08-31

## Context

The application has two legitimate audiences. Recruiters and contributors need to run the full
workflow locally without owning an AWS account. A deployed financial application needs centralized
identity, OAuth 2.0/OpenID Connect, short-lived access tokens, and TLS at every public boundary.

Using a fake bearer token or a committed demo password would make local setup easy but weaken the
security story. Requiring Cognito for local development would make the repository expensive and
difficult to evaluate.

## Decision

Authentication is selected once, through environment-specific settings.

Local development uses Django's standard authentication backend, an HttpOnly session cookie, and
CSRF protection on every unsafe request. The login and logout handlers are ordinary Django views
protected by `CsrfViewMiddleware`; they are not DRF API views because unauthenticated DRF session
requests do not automatically receive login CSRF protection. Basic authentication is not enabled.

Production uses Amazon Cognito's hosted authorization endpoint with Authorization Code + PKCE. The
React client is a public OAuth client and has no client secret. It sends only the access token to
the Django API.

The API accepts only RS256 bearer tokens whose signature and key ID resolve through the user pool's
cached JWKS. It validates the exact issuer, expiry, issued-at time, `token_use=access`, required
claims, and Cognito app-client ID. JWKS errors fail closed. The verified `sub` claim is the sole
external identity key; email is never used to attach an identity to an existing user.

Local password routes, demo-data commands, and Django admin are disabled in base and production
settings. Production settings refuse to start without the Cognito configuration.

## Consequences

- A reviewer can evaluate the product locally with no AWS cost or credentials.
- Local mutations demonstrate real browser cookie and CSRF behavior.
- Production API authorization is stateless and scales across ECS tasks.
- A compromised access token remains valid until it expires unless a separate revocation check is
  introduced; token lifetimes therefore need to stay short.
- Browser-held OAuth tokens remain exposed to successful script injection. The deployment must add
  a restrictive Content Security Policy and avoid third-party scripts.
- Cognito and local users share one database model, but identities never auto-link by mutable claims
  such as email or username.
- Tests must cover both transports because local session success does not prove JWT validation, and
  mocked browser tests do not prove Django's CSRF middleware.
