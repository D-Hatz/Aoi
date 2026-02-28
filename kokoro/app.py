import time
import logging

import gevent
from flask import Flask
from sqlalchemy import text

from .database import db, inspect_session, setup_pool_logging, set_route_bind


logger = logging.getLogger(__name__)


def create_app():
    app = Flask(__name__)

    app.config |= {
        "SQLALCHEMY_BINDS": {
            "other": {
                "url": "postgresql://postgres:postgres@localhost:5432/other_db",
                "pool_size": 1,
                "max_overflow": 0,
                "pool_timeout": 30,
                "pool_recycle": 1800,
                "pool_pre_ping": True,
                "isolation_level": "AUTOCOMMIT",
            },
            "default": {
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
        setup_pool_logging()

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
@set_route_bind("other")
def debug_route_bind_read():
    """
    Debug endpoint to verify read routing to "other" bind.
    
    Uses @set_route_bind("other") decorator to route queries
    to the read replica (other_db with AUTOCOMMIT isolation).
    
    Test:
        curl -s http://localhost:8000/read
    
    Expected: database="other_db", confirms routing works.
    """
    stmt = text("SELECT pg_backend_pid(), current_database()")
    result = db.session.execute(stmt).fetchone()

    info = inspect_session()
    info["pid"] = result[0]
    info["database"] = result[1]

    return info


@app.route("/write")
@set_route_bind("default")
def debug_route_bind_write():
    """
    Debug endpoint to verify write routing to "default" bind.
    
    Uses @set_route_bind("default") decorator to route queries
    to the primary database (postgres with transaction support).
    
    Test:
        curl -s http://localhost:8000/write
    
    Expected: database="postgres", confirms routing works.
    """
    stmt = text("SELECT pg_backend_pid(), current_database()")
    result = db.session.execute(stmt).fetchone()

    info = inspect_session()
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

    Expected: Same greenlet_id possible, but different session_id per request.
    """
    session = db.session()

    stmt = text("SELECT pg_sleep(3), pg_backend_pid(), current_database()")
    db.session.execute(stmt).fetchone()

    return {
        "greenlet_id": id(gevent.getcurrent()),
        "session_id": id(session),
        "session_class": session.__class__.__name__,
        "engine_bind": id(session.engine_bind) if session.engine_bind else None,
        "engine_bind_name": str(session.engine_bind.url)
        if session.engine_bind
        else None,
    }
