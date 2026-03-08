import time
import logging

import typing as t

import gevent
from flask import Flask
from sqlalchemy import select, text

from kokoro.models import User

from .database import db
from .sqlalchemy_decorators import set_route_bind, with_query_comment
from .sqlalchemy_contextmanager import query_comment
from .sqlalchemy_logging import setup_pool_logging
from .sqlalchemy_utils import inspect_session


logger = logging.getLogger(__name__)


def create_app():
    app = Flask(__name__)
    # TODO: check the autoflush option.
    app.config |= {
        "SQLALCHEMY_BINDS": {
            "replica": {
                "url": "postgresql://postgres:postgres@localhost:5432/other_db",
                "pool_size": 1,
                "max_overflow": 0,
                "pool_timeout": 30,
                "pool_recycle": 1800,
                "pool_pre_ping": True,
                "isolation_level": "AUTOCOMMIT",
                "skip_autocommit_rollback": True,
            },
            "primary": {
                "url": "postgresql://postgres:postgres@localhost:5432/postgres",
                "pool_size": 1,
                "max_overflow": 0,
                "pool_timeout": 30,
                "pool_recycle": 1800,
                "pool_pre_ping": True,
            },
        }
    }

    db.init_app(app)

    with app.app_context():
        setup_pool_logging(db)

    return app


app = create_app()


@app.route("/pool-contention")
def debug_pool_contention():
    """
    Debug endpoint to test connection pool exhaustion behavior.

    Executes a 3-second pg_sleep to hold a connection. With pool_size=1
    and max_overflow=0 per worker, each worker has 1 connection.

    To see pool contention, requests must exceed: workers * pool_size
    With 4 workers and pool_size=1, need 5+ concurrent requests.

    Test pool contention:
        for i in {1..9}; do curl -s http://localhost:8000/pool-contention & done; wait

    Expected:
        - First 4 requests: immediate (one per worker)
        - Requests 5-8: wait ~3s (waiting for pool)
        - Request 9: wait ~6s (second round of waiting)
    """
    start_time = time.time()

    stmt = text("SELECT pg_sleep(3), pg_backend_pid(), current_database()")
    result = db.session.execute(stmt).fetchone()

    database = result[2]

    duration = time.time() - start_time

    return f"Request completed in {round(duration, 2)} seconds on {database}\n"


@app.route("/read")
@set_route_bind("replica")
def debug_route_bind_read():
    """
    Debug endpoint to verify read routing to "replica" bind.

    Uses @set_route_bind("replica") decorator to route queries
    to the read replica (other_db with AUTOCOMMIT isolation).

    Test:
        curl -s http://localhost:8000/read

    Expected: database="other_db", confirms routing works.
    """
    stmt = text("SELECT pg_backend_pid(), current_database()")
    result = db.session.execute(stmt).fetchone()

    info = inspect_session(db)
    info["pid"] = result[0]
    info["database"] = result[1]

    return info


@app.route("/write")
@set_route_bind("primary")
def debug_route_bind_write():
    """
    Debug endpoint to verify write routing to "primary" bind.

    Uses @set_route_bind("primary") decorator to route queries
    to the primary database (postgres with transaction support).

    Test:
        curl -s http://localhost:8000/write

    Expected: database="postgres", confirms routing works.
    """
    stmt = text("SELECT pg_backend_pid(), current_database()")
    result = db.session.execute(stmt).fetchone()

    info = inspect_session(db)
    info["pid"] = result[0]
    info["database"] = result[1]

    return info


@app.route("/debug")
def debug_session():
    """
    Debug endpoint to verify session isolation per request.

    Sequential requests may reuse the same greenlet, but each request
    gets a new session instance (due to Flask-SQLAlchemy teardown calling
    scoped_session.remove() which clears the session from registry).

    From SQLAlchemy scoped_session.remove():
        "This will first call Session.close() method on the current Session,
        which releases any existing transactional/connection resources still
        being held; transactions specifically are rolled back. The Session
        is then discarded. Upon next usage within the same scope, the
        scoped_session will produce a new Session object."

    Test:
        curl -s http://localhost:8000/debug
        curl -s http://localhost:8000/debug

    Expected: Same greenlet_id possible, but different session_sequence_id per request.
    """

    session = db.session()

    stmt = text("SELECT pg_sleep(3), pg_backend_pid(), current_database()")
    session.execute(stmt).fetchone()

    return {
        "greenlet_id": id(gevent.getcurrent()),
        "session_sequence_id": session._unique_id,
        "session_id": id(session),
        "session_class": session.__class__.__name__,
        "engine_bind": id(session.engine_bind) if session.engine_bind else None,
        "engine_bind_name": str(session.engine_bind.url)
        if session.engine_bind
        else None,
    }


@app.route("/debug/session_identity")
def debug_session_identity():
    """
    Debug endpoint to verify scoped_session returns same instance within a request.

    scoped_session maintains a registry keyed by greenlet ID. Within the same
    greenlet (request), calling db.session() multiple times returns the SAME
    session instance.

    Test:
        curl -s http://localhost:8000/debug/session_identity

    Expected:
        - is_same_session: true
        - session_id == another_session_id
        - session_sequence_id == another_session_sequence_id
    """

    session = db.session()
    another_session = db.session()

    return {
        "session_id": id(session),
        "another_session_id": id(another_session),
        "is_same_session": session is another_session,
        "session_sequence_id": session._unique_id,
        "another_session_sequence_id": another_session._unique_id,
    }


@app.route("/inspect/session/engine/url")
def debug_inspect_session_engine_url():
    """
    Debug endpoint to verify bind switching within the same session.

    Demonstrates that set_bind() changes the engine URL returned by
    get_engine_url() while keeping the same session instance.

    Test:
        curl -s http://localhost:8000/inspect/session/engine/url

    Expected:
        - other_bind_url: postgresql://...other_db
        - default_bind_url: postgresql://...postgres
        - Same session_sequence_id for both (same session, different bind)
    """

    resp: dict[str, t.Any] = {}

    session = db.session()
    db.session.set_bind("replica")

    resp.update(
        {
            "replica_bind_url": {
                "url": db.session.get_engine_url(),
                "session_sequnece_id": session._unique_id,
                "session_id": id(session),
                "db_session_id": id(db.session),
            }
        }
    )

    db.session.set_bind("primary")
    resp.update(
        {
            "primary_bind_url": {
                "url": db.session.get_engine_url(),
                "session_sequnece_id": session._unique_id,
                "session_id": id(session),
                "db_session_id": id(db.session),
            }
        }
    )

    return resp


@app.route("/debug/comment/decorator")
@with_query_comment("endpoint=/debug/comment/decorator test=decorator")
def debug_comment_decorator():
    """
    Debug endpoint to test query commenting via decorator.

    Test:
        curl -s http://localhost:8000/debug/comment/decorator

    Check PostgreSQL logs for:
        /* endpoint=/debug/comment/decorator test=decorator */ SELECT ...
    """
    stmt = text("SELECT pg_backend_pid(), current_database()")
    result = db.session.execute(stmt).fetchone()

    return {
        "pid": result[0],
        "database": result[1],
        "comment_method": "decorator",
    }


@app.route("/debug/comment/contextmanager")
def debug_comment_contextmanager():
    """
    Debug endpoint to test query commenting via context manager.

    Test:
        curl -s http://localhost:8000/debug/comment/contextmanager

    Check PostgreSQL logs for:
        /* endpoint=/debug/comment/contextmanager test=contextmanager */ SELECT ...
    """
    with query_comment("endpoint=/debug/comment/contextmanager test=contextmanager"):
        stmt = text("SELECT pg_backend_pid(), current_database()")
        result = db.session.execute(stmt).fetchone()

    return {
        "pid": result[0],
        "database": result[1],
        "comment_method": "contextmanager",
    }


@app.route("/debug/release-connection")
def debug_release_connection():
    """
    Debug endpoint to verify early connection release mid-request.

    Demonstrates that calling session.close() returns the connection to the pool
    immediately, without waiting for request teardown. The session is re-usable
    afterwards — the next query transparently acquires a new connection.

    This is useful when a request does a SELECT and then calls external services,
    avoiding holding a connection idle during that time.

    Pool log sequence expected:
        Checkout  → first SELECT acquires connection
        Checkin   → session.close() releases it back to pool
        Checkout  → second SELECT (pg_sleep) acquires a new connection
        Checkin   → request teardown releases it

    Test:
        curl -s http://localhost:8000/debug/release-connection
    """

    db.session.execute(text("SELECT current_database(), pg_backend_pid()")).fetchone()
    db.session.close()  # Explicitly release connection back to pool

    # After closing the session, the scoped_session should acquire a new connection from the pool for the next query.
    db.session.execute(
        text("SELECT pg_sleep(3), pg_backend_pid(), current_database()")
    ).fetchone()

    return {
        "message": "Executed query after releasing connection. Check pool logs for connection lifecycle events."
    }


@app.route("/debug/orm-bind-leak")
def debug_orm_bind_leak():
    """
    Demonstrates silent write leak when switching binds mid-session with a shared ORM object.

    A User is loaded from primary. The bind is then switched to replica before committing
    a change. Because the ORM object is tracked by the session (not the bind), SQLAlchemy
    flushes the UPDATE to whatever bind is active at commit time — the replica.

    This is a non-obvious side effect: if the replica allows writes (e.g. same PG user,
    no read-only constraint), the write silently goes to the wrong database with no error.

    The fix is to always commit before switching binds, or close the session and start
    fresh on the target bind.

    Seed data:
        psql postgresql://postgres:postgres@localhost:5432/postgres -c "INSERT INTO users (name, email, created_at, updated_at) VALUES ('Test User', 'test@example.com', NOW(), NOW());"
        psql postgresql://postgres:postgres@localhost:5432/other_db -c "INSERT INTO users (name, email, created_at, updated_at) VALUES ('Test User', 'test@example.com', NOW(), NOW());"

    Test:
        curl -s http://localhost:8000/debug/orm-bind-leak

    Expected (check pg logs):
        SELECT → [primary]
        UPDATE → [replica]   ← write leaked to wrong database
        COMMIT → [primary]
    """

    db.session.set_bind("primary")
    stmt = select(User).where(User.name == "Test User")
    # the object was fetched from the primary.
    user = db.session.execute(stmt).scalar_one_or_none()

    db.session.set_bind("replica")

    user.email = "test@example.com"
    db.session.commit()

    return {
        "message": "the object is shared in session, so there no conflict on commit."
    }
