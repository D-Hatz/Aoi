import time
import logging

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


@app.route("/io")
def io_bound_task():
    start_time = time.time()

    stmt = text("SELECT pg_sleep(3), pg_backend_pid(), current_database()")
    result = db.session.execute(stmt).fetchone()

    database = result[2]

    duration = time.time() - start_time

    return f"I/O task completed in {round(duration, 2)} seconds on {database}\n"


@app.route("/bind/<bind_name>")
def test_bind(bind_name):
    if bind_name == "default":
        db.session.set_bind(None)
    else:
        db.session.set_bind(bind_name)

    stmt = text("SELECT pg_backend_pid(), current_database()")
    result = db.session.execute(stmt).fetchone()

    info = inspect_session()
    info["pid"] = result[0]
    info["database"] = result[1]

    return info


@app.route("/read")
@set_route_bind("other")
def test_read():
    stmt = text("SELECT pg_backend_pid(), current_database()")
    result = db.session.execute(stmt).fetchone()

    info = inspect_session()
    info["pid"] = result[0]
    info["database"] = result[1]

    return info


@app.route("/write")
@set_route_bind("default")
def test_write():
    stmt = text("SELECT pg_backend_pid(), current_database()")
    result = db.session.execute(stmt).fetchone()

    info = inspect_session()
    info["pid"] = result[0]
    info["database"] = result[1]

    return info
