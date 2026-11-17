# Query Clinic

A PostgreSQL performance lab: measure a query, test an index, and compare execution plans while verifying identical results. Built with FastAPI, PostgreSQL 16, and a responsive dashboard. No model or API key required.

## Start

Requires Docker with Compose:

```bash
docker compose up --build -d
```

Open **http://localhost:8000**. The application seeds 5,000 customers, 200 products, and 100,000 orders automatically. First startup downloads images and dependencies. Data persists in a Docker volume. Stop with `docker compose down`.

## Experiments

| Query | Index tested | Purpose |
| --- | --- | --- |
| Customer history | Customer + descending date/ID | Filter and return ordered history |
| Daily paid revenue | Partial date index with included columns | Restrict paid-order aggregation |
| Pending queue | Partial date/ID index | Retrieve oldest 50 pending orders |

The schema uses primary keys, unique customer emails, foreign keys, positive quantity/price checks, and constrained order statuses. Prices use exact numeric values.

Each experiment warms both variants, measures 3–9 executions with `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)`, compares medians, and hashes ordered result rows. It stores timing samples, complete plans, query parameters, index recommendations, and tradeoffs. Download JSON evidence from the dashboard. `/api/runs` returns the last 20 reports.

Experiments acquire a PostgreSQL advisory lock and hold writes to the orders/products tables during comparison. Index DDL runs in a transaction that always rolls back, including on failure. Only evidence is committed afterward. The planner remains free to choose its preferred plan; the app never forces index use or guarantees a speedup.

Measurements use a fixed synthetic dataset and baseline-first warm-cache ordering. They are a teaching comparison, not a production benchmark or proof of general performance. Existing non-Clinic indexes can influence results. Use a dedicated demo database.

## Test against real PostgreSQL

```bash
docker compose exec web pytest -q
```

The suite checks seeding, foreign keys, check constraints, atomic rollback, result equivalence for all three queries, index cleanup after success and failure, persistence, and HTTP validation. It does not assert a minimum speedup because timings depend on hardware and cache.

## Local Python development

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL='postgresql://USER:PASSWORD@HOST:5432/DATABASE'
python clinic.py seed
uvicorn app:app --reload --host 127.0.0.1
pytest -q
```

Without DATABASE_URL, database tests are explicitly skipped; validation tests still run. Interactive API documentation: `/docs`. CLI: `python clinic.py benchmark --case daily_revenue`.

## Scope

This local lab exposes only three fixed parameterized queries, not arbitrary SQL. It has no authentication and is bound to localhost in Compose. The Compose password is a public local-demo credential. Do not expose it as a production service or point it at a production database. Seeding is idempotent for the supplied dataset; it is not a production migration system.

The user's earlier custom test steps are not available in this thread; the test suite documents the checks actually implemented.

Measured results and environment details: see `VALIDATION.md`.
