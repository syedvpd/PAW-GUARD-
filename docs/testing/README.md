# Testing Strategy

## Overview

PawGuard implements a comprehensive testing strategy across multiple levels: unit, integration, end-to-end, regression, smoke, and load testing.

## Test Structure

```
tests/
  unit/           # Isolated component tests
  integration/    # API endpoint tests with database
  e2e/            # Full workflow tests
  regression/     # PRR acceptance criteria
  smoke/          # Quick health checks
  load/           # Performance testing (Locust)
  conftest.py     # Shared fixtures
  auth_helpers.py # Authentication utilities
```

## Test Types

### Unit Tests
**Location**: `tests/unit/`

Isolated tests for individual components:
- Service logic
- Repository queries
- Schema validation
- Utility functions
- Business rules

**Example**:
```python
async def test_rescue_service_verify_request():
    # Test rescue verification logic
    ...
```

### Integration Tests
**Location**: `tests/integration/`

API endpoint tests with database:
- HTTP request/response
- Authentication/authorization
- Database operations
- Cross-module interactions

**Example**:
```python
async def test_rescue_api_create():
    response = await client.post("/api/v1/rescue", json={...})
    assert response.status_code == 201
```

### End-to-End Tests
**Location**: `tests/e2e/`

Full workflow tests:
- Complete business flows
- Multiple API calls
- State transitions
- Side effects verification

**Example**:
```python
async def test_rescue_workflow():
    # Report -> Verify -> Dispatch -> Admit
    ...
```

### Regression Tests
**Location**: `tests/regression/`

PRR (Product Requirements) acceptance criteria:
- Specific feature validation
- Edge case coverage
- Security requirements

**Example**:
```python
async def test_prr_rescue_severity():
    # Verify severity prioritization
    ...
```

### Smoke Tests
**Location**: `tests/smoke/`

Quick health checks:
- Application startup
- Database connectivity
- Redis connectivity
- Basic endpoint availability

### Load Tests
**Location**: `tests/load/`

Performance testing with Locust:
- Concurrent users
- Response times
- Throughput
- Error rates

## Running Tests

### All Tests
```bash
uv run pytest
```

### Unit Tests Only
```bash
uv run pytest tests/unit/
```

### Integration Tests
```bash
uv run pytest tests/integration/
```

### E2E Tests
```bash
uv run pytest tests/e2e/
```

### Specific Test File
```bash
uv run pytest tests/unit/test_rescue.py
```

### With Coverage
```bash
uv run pytest --cov=pawguard --cov-report=html
```

## Test Configuration

### pytest.ini
```ini
[pytest]
asyncio_mode = auto
testpaths = ["tests"]
pythonpath = [".", "src"]
```

### Conftest Fixtures
```python
# tests/conftest.py
- async_client: HTTPX AsyncClient
- db_session: AsyncSession
- redis_client: RedisClient
- authenticated_user: CurrentUser
```

### Auth Helpers
```python
# tests/auth_helpers.py
- create_test_user()
- get_auth_headers()
- login_as_role()
```

## Test Database

### Setup
- Uses SQLite in-memory for unit tests
- Uses PostgreSQL for integration tests
- Isolated per test (transaction rollback)

### Fixtures
```python
@pytest.fixture
async def db_session():
    async with AsyncSessionLocal() as session:
        yield session
        await session.rollback()
```

## Mocking Strategy

### External Services
- Redis: `fakeredis` or mocked client
- S3: Mocked boto3 client
- Email: Mocked Brevo API
- FCM: Mocked Firebase Admin

### Database
- Unit tests: SQLite in-memory
- Integration tests: Real PostgreSQL (test database)

## Code Quality

### Linting
```bash
uv run ruff check src/ tests/
```

### Type Checking
```bash
uv run mypy src/
```

### Security Scanning
```bash
uv run bandit -r src/
```

## CI/CD Integration

### GitHub Actions
```yaml
- name: Run Tests
  run: uv run pytest --cov=pawguard

- name: Lint
  run: uv run ruff check src/ tests/

- name: Type Check
  run: uv run mypy src/
```

## Coverage Requirements

- Minimum 80% code coverage
- Critical paths: 95%+ coverage
- Security-related code: 100% coverage

## Test Data

### Factories
```python
# tests/e2e/factories.py
- UserFactory
- RescueFactory
- DogFactory
- AdoptionFactory
```

### Seeds
```python
# scripts/seed_*.py
- seed_roles_and_permissions.py
- seed_dogs.py
- seed_found_reports.py
```

## Best Practices

1. **Isolation**: Each test independent, no shared state
2. **Deterministic**: Same results every run
3. **Fast**: Unit tests < 1s, integration < 5s
4. **Readable**: Clear test names and assertions
5. **Maintainable**: DRY, use fixtures and factories

## Debugging Failed Tests

### Verbose Output
```bash
uv run pytest -v tests/unit/test_rescue.py
```

### Stop on First Failure
```bash
uv run pytest -x
```

### Interactive Debugger
```bash
uv run pytest --pdb
```

### Print Statements
```python
async def test_example():
    print(f"Result: {result}")
    assert result == expected
```
