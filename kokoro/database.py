import logging
import typing as t

import sqlalchemy as sa
from flask_sqlalchemy import SQLAlchemy
from flask_sqlalchemy.session import Session
from sqlalchemy.exc import UnboundExecutionError

from .sequence import FileSequence


session_sequence = FileSequence("logs/session_sequence.txt")


COMMENT_ATTRIBUTE = "comment"


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
        self.session.get_engine_url = (
            lambda: self.session().get_bind().url.render_as_string(hide_password=True)
            if self.session().get_bind()
            else None
        )


class RouteSession(Session):
    def __init__(self, db: SQLAlchemy, **kwargs: t.Any) -> None:
        super().__init__(db, **kwargs)
        self.engine_bind: sa.engine.Engine | None = None
        self._unique_id = session_sequence.next()

    def __repr__(self) -> str:
        return f"<RouteSession(id={self._unique_id})>"

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
            return self._db.engines.get("primary")

    def set_bind(self, bind: sa.engine.Engine | sa.engine.Connection | str):
        """Override the bind to use for this session."""
        if isinstance(bind, str):
            self.engine_bind = self._db.engines.get(bind)
        else:
            self.engine_bind = bind



@sa.event.listens_for(sa.Engine, "before_cursor_execute", retval=True)
def _apply_comment(connection, cursor, statement, parameters, context, executemany):
    """
    Apply comments to statements.

    We intercept all statement executions at the cursor level, where the
    before_cursor_execute() event gives us the final string SQL statement
    in all cases and also gives us a chance to modify the string.

    Based on: https://github.com/sqlalchemy/sqlalchemy/wiki/SessionModifiedSQL
    """

    session_info = connection.info.get("session_info", {})

    if COMMENT_ATTRIBUTE in session_info:
        comment = session_info[COMMENT_ATTRIBUTE]
        statement = f"/* {comment} */ {statement}"

    return statement, parameters


@sa.event.listens_for(RouteSession, "after_begin")
def _connection_for_session(session, trans, connection):
    """Share the 'info' dictionary of Session with Connection
    objects.

    This occurs as new Connection objects are associated with the
    Session.   The .info dictionary on Connection is local to the
    DBAPI connection.

    """
    connection.info["session_info"] = session.info


db = RouteSQLAlchemy(session_options={"class_": RouteSession})
