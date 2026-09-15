from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

from werkzeug.security import (
    generate_password_hash,
    check_password_hash,
)


db = SQLAlchemy()


# =========================================================
# 利用者
# =========================================================

class User(
    UserMixin,
    db.Model
):

    __tablename__ = "users"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    name = db.Column(
        db.String(100),
        nullable=False
    )

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

    role = db.Column(
        db.String(20),
        nullable=False,
        default="user"
    )

    status = db.Column(
        db.String(20),
        nullable=False,
        default="pending"
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(
            timezone.utc
        )
    )


    # -----------------------------------------------------
    # パスワード設定
    # -----------------------------------------------------

    def set_password(
        self,
        password
    ):

        self.password_hash = (
            generate_password_hash(
                password
            )
        )


    # -----------------------------------------------------
    # パスワード確認
    # -----------------------------------------------------

    def check_password(
        self,
        password
    ):

        return check_password_hash(
            self.password_hash,
            password
        )


    # -----------------------------------------------------
    # 管理者判定
    # -----------------------------------------------------

    @property
    def is_admin(self):

        return self.role == "admin"



# =========================================================
# 部屋
# =========================================================

class Room(
    db.Model
):

    __tablename__ = "rooms"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    name = db.Column(
        db.String(200),
        nullable=False
    )

    capacity = db.Column(
        db.Integer,
        nullable=False
    )

    # -----------------------------------------------------
    # 貸切利用かどうか
    #
    # False:
    #   電子情報計算機実習室など
    #   定員以内なら複数グループが同時利用可能
    #
    # True:
    #   メディア工学研究室2など
    #   同時間帯には1件のみ予約可能
    # -----------------------------------------------------

    exclusive = db.Column(
        db.Boolean,
        nullable=False,
        default=False
    )



# =========================================================
# 予約
# =========================================================

class Reservation(
    db.Model
):

    __tablename__ = "reservations"

    id = db.Column(
        db.Integer,
        primary_key=True
    )


    # -----------------------------------------------------
    # 部屋
    # -----------------------------------------------------

    room_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "rooms.id"
        ),
        nullable=False,
        index=True
    )


    # -----------------------------------------------------
    # 利用者
    # -----------------------------------------------------

    user_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "users.id"
        ),
        nullable=False,
        index=True
    )


    # -----------------------------------------------------
    # 利用日時
    # -----------------------------------------------------

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


    # -----------------------------------------------------
    # 利用人数
    # -----------------------------------------------------

    people = db.Column(
        db.Integer,
        nullable=False
    )


    # -----------------------------------------------------
    # 利用目的・備考
    # -----------------------------------------------------

    purpose = db.Column(
        db.String(255),
        nullable=True
    )

    note = db.Column(
        db.Text,
        nullable=True
    )


    # -----------------------------------------------------
    # 複数日程をまとめた申請ID
    # -----------------------------------------------------

    batch_id = db.Column(
        db.String(36),
        nullable=True,
        index=True
    )


    # -----------------------------------------------------
    # 状態
    #
    # pending
    # approved
    # rejected
    # cancelled
    # -----------------------------------------------------

    status = db.Column(
        db.String(20),
        nullable=False,
        default="pending",
        index=True
    )


    # -----------------------------------------------------
    # 申請日時
    # -----------------------------------------------------

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(
            timezone.utc
        )
    )


    # -----------------------------------------------------
    # 承認情報
    # -----------------------------------------------------

    approved_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True
    )

    approved_by = db.Column(
        db.Integer,
        nullable=True
    )


    # -----------------------------------------------------
    # 却下情報
    # -----------------------------------------------------

    rejected_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True
    )

    rejected_by = db.Column(
        db.Integer,
        nullable=True
    )


    # -----------------------------------------------------
    # リレーション
    # -----------------------------------------------------

    room = db.relationship(
        "Room",
        backref="reservations"
    )

    user = db.relationship(
        "User",
        backref="reservations"
    )

