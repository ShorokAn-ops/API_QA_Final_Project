# API Test Plan - ERPNext Risk Analyzer

## What to test

### Core Endpoints

- **GET /health**: Verify API availability
- **GET /invoices**: Success with valid parameters (limit, include_items) and edge cases (max limit, empty database)
- **GET /dashboard/summary**: Success (returns risk counts and totals) and caching behavior
- **GET /risk/anomalies**: Success with different min_rate values and empty results
- **GET /risk/vendors**: Success (vendor statistics with risk counts) and empty database case
- **POST /sync/run**: Success (sync completes) and cache invalidation after sync
- **POST /risk/recalculate**: Success (risk recalculation) and cache clearing

### Data Validation

- Invoice data structure and relationships (items, risk)
- Risk calculation accuracy (LOW, MEDIUM, HIGH, CRITICAL levels)
- Database persistence after sync operations

## Test strategy

Integration tests using FastAPI TestClient with real SQLite database.

- **Database tests**: Test with actual database connections to verify queries and data persistence
- **Live ERP tests**: Test real ERPNext instance for sync validation
- Tests are written with `pytest` framework
- Mock external services when needed (ERP client, AI risk service)

## Environment

- **Local execution**: SQLite database in test mode
- **Test isolation**: Each test uses fresh database state via fixtures (conftest.py)
- **CI/CD**: Automated execution in GitHub Actions or similar pipeline

## Success & reporting

- All critical API endpoints covered by automated tests
- Code coverage measured with `pytest-cov`
- Coverage report generated in XML format (coverage.xml)
- Minimum acceptable coverage: 90% for core business logic
- Test results displayed in terminal with pass/fail status
