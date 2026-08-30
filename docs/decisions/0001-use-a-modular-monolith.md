# ADR 0001: Use a modular monolith

- Status: Accepted
- Date: 2026-08-25

## Context

The application needs consistent writes across transactions, imports, categorization rules, and
budgets. One developer owns the project, and none of the initial features require independent
deployment or scaling.

## Decision

Use one Django REST Framework service organized into domain-focused Django apps, one React client,
and one PostgreSQL database.

Keep HTTP views thin. Put multi-step business operations in explicit service functions, reporting
queries in selectors, request validation in serializers, and durable invariants in models and
database constraints.

## Consequences

- Local development, transactions, testing, and deployment remain straightforward.
- Domain boundaries are visible without introducing network calls or distributed transactions.
- The API must be deployed as one unit.
- A domain can be extracted later only if measured scaling or ownership needs justify it.

