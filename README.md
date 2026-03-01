# アオイ (Aoi)

Flask + SQLAlchemy + gevent reference implementation.

## TODO: Database Features

### High Priority
- [ ] **Statement Timeout** - Prevent runaway queries with `@with_statement_timeout(ms)` decorator
- [ ] **Query Count Per Request** - Track queries per request, warn if > N, add `X-Query-Count` header
- [ ] **Slow Query Logging** - Auto-log queries exceeding threshold with EXPLAIN ANALYZE

### Medium Priority
- [ ] **N+1 Detection** - Detect and warn about N+1 query patterns
- [ ] **Strict Loading** - `raiseload('*')` option to prevent accidental lazy loading
- [ ] **Advisory Locks** - `@with_advisory_lock("key")` for distributed locking

### Low Priority
- [ ] **Query Caching** - Cache identical queries within a request
- [ ] **Explain/Analyze Helper** - Easy query plan inspection for debugging

### Done
- [x] Query comments (`@with_query_comment`, `query_comment()`)
- [x] Read/write routing (`@set_route_bind`)
- [x] Connection pool logging (`setup_pool_logging()`)
- [x] Session inspection (`inspect_session()`)

---

## Setup

### PostgreSQL

```bash
docker run -d \
  --name kokoro-postgres \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -p 5432:5432 \
  postgres:16

# Create second database
docker exec kokoro-postgres psql -U postgres -c "CREATE DATABASE other_db;"
```

### PostgreSQL Logging

```bash
docker exec kokoro-postgres psql -U postgres -c "ALTER SYSTEM SET log_statement = 'all';"
docker exec kokoro-postgres psql -U postgres -c "SELECT pg_reload_conf();"
docker logs -f kokoro-postgres
```

## Run Application

```bash
OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES gunicorn 'kokoro.app:app' -c gunicorn.conf.py --capture-output
```

## Test Endpoints

```bash
# Query comment - decorator
curl -s http://localhost:8000/debug/comment/decorator

# Query comment - context manager
curl -s http://localhost:8000/debug/comment/contextmanager

# Read routing (other_db)
curl -s http://localhost:8000/read

# Write routing (postgres)
curl -s http://localhost:8000/write

# Pool contention test
for i in {1..9}; do curl -s http://localhost:8000/pool-contention & done; wait
```