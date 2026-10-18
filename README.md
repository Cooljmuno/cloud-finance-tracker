# Cloud Finance Tracker

[![CI](https://github.com/Cooljmuno/cloud-finance-tracker/actions/workflows/ci.yml/badge.svg)](https://github.com/Cooljmuno/cloud-finance-tracker/actions/workflows/ci.yml)

A full-stack app for tracking transactions, organizing expenses, and understanding monthly spending.

**Stack:** React · TypeScript · Python / Django REST Framework · PostgreSQL · AWS · Terraform · Docker · GitHub Actions

## What it does

- **Track:** Manage accounts, categories, and transactions.
- **Import:** Preview CSV statements and avoid importing the same file twice.
- **Automate:** Categorize purchases with custom rules.
- **Plan:** Set monthly budgets and view spending trends.

Each user sees only their own financial records. All demo data is synthetic.

## Built and tested

GitHub Actions runs Pytest, Vitest, and Playwright checks. A real AWS deployment passed **54 live checks**, covering authentication, imports, budgets, reports, and user isolation.

The temporary deployment was removed after the demo to keep costs low. [View deployment evidence](docs/evidence/2026-10-18-aws-demo.md).

## Run locally

With Docker Desktop running, use these commands from the repository root for first-time setup:

```bash
cp .env.example .env
docker compose up --build -d --wait --wait-timeout 120
docker compose exec backend python manage.py seed_demo_data
```

Choose a password when prompted. Open [localhost:5173](http://localhost:5173) and sign in as `portfolio-demo`.

[Development and API guide](docs/development.md) · [Architecture decisions](docs/decisions) · [AWS deployment](docs/deployment.md)
