# Cloud Finance Tracker

A full-stack finance application for importing synthetic transaction data, applying deterministic
categorization rules, tracking monthly budgets, and visualizing spending. The project is being built
as a production-shaped portfolio system with explicit architecture and security decisions.

## Current milestone: foundation

The repository currently provides:

- a Django 5.2 LTS and Django REST Framework API;
- a custom UUID user model prepared for Cognito identities;
- a React 19 and TypeScript client built with Vite;
- PostgreSQL 18 through Docker Compose;
- a database-aware `GET /api/v1/health/` endpoint;
- Pytest, Vitest, and Playwright smoke tests; and
- GitHub Actions gates for linting, tests, production builds, and Docker images.

## Architecture

```text
React SPA  --->  Django REST API  --->  PostgreSQL
  :5173              :8000                :5432
```

This is a modular monolith. Django apps will separate users, transactions, imports, categorization,
and budgets while sharing one API deployment and one relational database. See
[`docs/decisions`](docs/decisions) for the recorded tradeoffs.

## Prerequisites

- Docker Desktop
- Git
- Node.js 24.19 if running the frontend outside Docker
- Python 3.14 and `uv` if running the backend outside Docker

Docker Desktop supports Apple Silicon directly. Do not force `linux/amd64` for local development.

## Start the complete local stack

```bash
cp .env.example .env
docker compose up --build
```

Then open:

- React client: <http://localhost:5173>
- API health check: <http://localhost:8000/api/v1/health/>
- Django admin: <http://localhost:8000/admin/>

Stop the containers with `docker compose down`. The named PostgreSQL volume preserves local data.
Use `docker compose down --volumes` only when you intentionally want to erase that local database.

## Run checks without Docker

Backend:

```bash
cd backend
uv sync
uv run ruff check .
uv run ruff format --check .
uv run python manage.py makemigrations --check --dry-run
uv run pytest
```

Frontend:

```bash
cd frontend
npm ci
npm run lint
npm run typecheck
npm test
npm run build
npx playwright install chromium
npm run test:e2e
```

Pytest uses an in-memory SQLite database when PostgreSQL environment variables are absent. CI and
the Docker stack use PostgreSQL so database integration is still tested against the production
database engine.

## Next milestone

Add the first complete transaction slice: financial accounts, categories, transactions, per-user
query isolation, and a React transaction table backed by PostgreSQL.

## Data policy

Use only synthetic transaction data in development, tests, screenshots, and demonstrations. Never
commit personal financial records or credentials.

