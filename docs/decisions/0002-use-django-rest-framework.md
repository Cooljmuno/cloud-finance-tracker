# ADR 0002: Use Django REST Framework

- Status: Accepted
- Date: 2026-08-25

## Context

The project needs a relational data model, migrations, an administrative interface, API validation,
permissions, and integration with an external OpenID Connect provider.

## Decision

Use Django 5.2 LTS and Django REST Framework for the backend API.

## Consequences

- Django supplies an integrated ORM, migrations, admin, and established application conventions.
- Django REST Framework supplies serializers, authentication hooks, permissions, and API views.
- The framework is heavier than FastAPI and some behavior is implicit, so service boundaries and
  tests must keep business logic understandable.
- Django 5.2 LTS receives security support through April 2028.

