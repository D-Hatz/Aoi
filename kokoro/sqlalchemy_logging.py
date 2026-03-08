"""
SQLAlchemy logging utilities.

Provides connection pool logging for debugging and monitoring.
"""

import gevent
from sqlalchemy import event
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime


def setup_pool_logging(db: SQLAlchemy) -> None:
    """
    Set up connection pool logging for all engines.

    Logs connection lifecycle events:
    - New connection created
    - Connection checked out (with greenlet ID)
    - Connection checked in (with greenlet ID)

    Args:
        db: The SQLAlchemy instance to set up logging for

    Usage:
        with app.app_context():
            setup_pool_logging(db)
    """
    for bind_name, engine in db.engines.items():
        name = bind_name if bind_name is not None else "primary"

        @event.listens_for(engine, "connect")
        def on_connect(dbapi_conn, connection_record, _name=name):
            print(f"[POOL:{_name}_{datetime.now()}] New connection: {id(dbapi_conn)}")

        @event.listens_for(engine, "checkout")
        def on_checkout(dbapi_conn, connection_record, connection_proxy, _name=name):
            gid = id(gevent.getcurrent())
            print(
                f"[POOL:{_name}_{datetime.now()}] Checkout conn={id(dbapi_conn)} greenlet={gid}"
            )

        @event.listens_for(engine, "checkin")
        def on_checkin(dbapi_conn, connection_record, _name=name):
            gid = id(gevent.getcurrent())
            print(
                f"[POOL:{_name}_{datetime.now()}] Checkin conn={id(dbapi_conn)} greenlet={gid}"
            )
