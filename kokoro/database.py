import logging
import typing as t

import sqlalchemy as sa
from flask_sqlalchemy import SQLAlchemy
from flask_sqlalchemy.session import Session
from sqlalchemy import event
from sqlalchemy.exc import UnboundExecutionError

from functools import wraps


logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


class RouteSQLAlchemy(SQLAlchemy):
    def __init__(self, *args, **kwargs):
        """
        Initialize RouteSQLAlchemy.

        See flask_sqlalchemy.SQLAlchemy.__init__ for parameters.
        """
        super().__init__(*args, **kwargs)
        self.session.set_bind = lambda bind: self.session().set_bind(bind)


class RouteSession(Session):
    def __init__(self, db: SQLAlchemy, **kwargs: t.Any) -> None:
        super().__init__(db, **kwargs)
        self.engine_bind: sa.engine.Engine | None = None

    def get_bind(
        self,
        mapper: t.Any | None = None,
        clause: t.Any | None = None,
        bind: sa.engine.Engine | sa.engine.Connection | None = None,
        **kwargs: t.Any,
    ) -> sa.engine.Engine | sa.engine.Connection:
        """
        Select an engine based on the ``bind_key`` of the metadata associated with
        the model or table being queried. If no bind key is set, uses the default bind.
        """

        if self.engine_bind is not None:
            return self.engine_bind

        try:
            selected_bind = super().get_bind(mapper, clause, bind, **kwargs)
        except UnboundExecutionError:
            selected_bind = None

        if selected_bind is None:
            return self._db.engines.get("default")

    def set_bind(self, bind: sa.engine.Engine | sa.engine.Connection | str):
        """Override the bind to use for this session."""
        if isinstance(bind, str):
            self.engine_bind = self._db.engines.get(bind)
        else:
            self.engine_bind = bind


def setup_pool_logging():
    """Log connection pool activity per engine."""
    import gevent

    for bind_name, engine in db.engines.items():
        name = bind_name if bind_name is not None else "default"

        @event.listens_for(engine, "connect")
        def on_connect(dbapi_conn, connection_record, _name=name):
            print(f"[POOL:{_name}] New connection: {id(dbapi_conn)}")

        @event.listens_for(engine, "checkout")
        def on_checkout(dbapi_conn, connection_record, connection_proxy, _name=name):
            gid = id(gevent.getcurrent())
            print(f"[POOL:{_name}] Checkout conn={id(dbapi_conn)} greenlet={gid}")

        @event.listens_for(engine, "checkin")
        def on_checkin(dbapi_conn, connection_record, _name=name):
            gid = id(gevent.getcurrent())
            print(f"[POOL:{_name}] Checkin conn={id(dbapi_conn)} greenlet={gid}")


def inspect_session():
    """Show session and pool stats"""
    info = {
        "default_bind": str(db.session.get_bind().url),
        "session_id": id(db.session),
        "is_active": db.session.is_active,
        "pools": {},
    }

    for bind_name, engine in db.engines.items():
        key = bind_name if bind_name is not None else "default"
        pool = engine.pool
        info["pools"][key] = {
            "url": str(engine.url),
            "is_default": db.session.get_bind() is engine,
            "pool_size": pool.size(),
            "checked_out": pool.checkedout(),
            "checked_in": pool.checkedin(),
            "overflow": pool.overflow(),
        }

    return info


db = RouteSQLAlchemy(session_options={"class_": RouteSession})


def set_route_bind(bind_name: str):
    """
    Decorator to route all database queries in a request to a specific bind.
    
    Sets the session's engine_bind before the route executes, and restores
    the original bind after completion (even if an exception occurs).
    
    Args:
        bind_name: Name of the bind (must exist in SQLALCHEMY_BINDS)
    
    Usage:
        @app.route("/read")
        @set_route_bind("replica")
        def read_data():
            return db.session.execute(text("SELECT ...")).fetchall()
    
    Note:
        Decorator order matters - @set_route_bind must come AFTER @app.route
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            original_bind = db.session.get_bind()
            db.session.set_bind(bind_name)
            try:
                return func(*args, **kwargs)
            finally:
                db.session.set_bind(original_bind)

        return wrapper

    return decorator
