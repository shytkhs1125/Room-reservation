from datetime import datetime, timezone

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash


db = SQLAlchemy()


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(100), nullable=False)

    email = db.Column(
        db.String(255),
        unique=True,
        nullable=False,
        index=True
    )

    password_hash = db.Column(
        db.String(255),
        nullable=False
    )

    # user / admin
    role = db.Column(
        db.String(20),
        nullable=False,
        default="user"
    )

    # pending / active / rejected
    status = db.Column(
        db.String(20),
        nullable=False,
        default="pending"
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(
            self.password_hash,
            password
        )

    @property
    def is_admin(self):
        return self.role == "admin"


class Room(db.Model):
    __tablename__ = "rooms"

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(
        db.String(200),
        nullable=False
    )

    capacity = db.Column(
        db.Integer,
        nullable=False,
        default=20
    )


class Reservation(db.Model):
    __tablename__ = "reservations"

    id = db.Column(db.Integer, primary_key=True)

    room_id = db.Column(
        db.Integer,
        db.ForeignKey("rooms.id"),
        nullable=False
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False
    )

    start_datetime = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        index=True
    )

    end_datetime = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        index=True
    )

    people = db.Column(
        db.Integer,
        nullable=False
    )

    purpose = db.Column(
        db.String(255),
        nullable=True
    )

    note = db.Column(
        db.Text,
        nullable=True
    )


    batch_id = db.Column(
        db.String(36),
        nullable=True,
        index=True
    )
    
    # pending / approved / rejected / cancelled
    status = db.Column(
        db.String(20),
        nullable=False,
        default="pending",
        index=True
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )

    approved_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True
    )

    approved_by = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=True
    )

    rejected_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True
    )

    rejected_by = db.Column(
        db.Integer,
        nullable=True
    )
    
    user = db.relationship(
        "User",
        foreign_keys=[user_id]
    )

    room = db.relationship("Room")
    