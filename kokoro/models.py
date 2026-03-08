import uuid
from datetime import datetime
from datetime import timezone
from .database import db


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    version = db.Column(db.Uuid, nullable=False, default=uuid.uuid4)
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        default=datetime.now(timezone.utc),
        onupdate=datetime.now(timezone.utc),
    )

    __mapper_args__ = {
        "version_id_col": version,
        "version_id_generator": lambda version: uuid.uuid4(),
    }

    def __repr__(self):
        return f"<User(id={self.id}, name={self.name})>"
