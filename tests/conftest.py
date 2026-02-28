import pytest
from flask import Flask
from flask.testing import FlaskClient

from kokoro.app import create_app
from kokoro.database import db


@pytest.fixture
def app() -> Flask:
    """Create test application."""
    app = create_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    """Create test client."""
    return app.test_client()


@pytest.fixture
def db_session(app: Flask):
    """Get database session within app context."""
    with app.app_context():
        yield db.session
        db.session.rollback()
