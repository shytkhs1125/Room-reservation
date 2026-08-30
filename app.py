import os
import uuid
from datetime import datetime, date
from zoneinfo import ZoneInfo
import smtplib
from email.message import EmailMessage
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from dotenv import load_dotenv

from flask import (
    Flask,
    render_template,
    redirect,
    url_for,
    request,
    flash,
    jsonify,
)

from flask_login import (
    LoginManager,
    login_user,
    logout_user,
    login_required,
    current_user,
)

from flask_wtf.csrf import CSRFProtect

from sqlalchemy import text

from models import db, User, Room, Reservation


# =========================================================
# 基本設定
# =========================================================

load_dotenv()

app = Flask(__name__)

app.config["SECRET_KEY"] = os.environ["SECRET_KEY"]
app.config["SESSION_COOKIE_NAME"] = "__session"
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ["DATABASE_URL"]

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False


# Supabaseへの接続数を抑える
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_size": 3,
    "max_overflow": 2,
    "pool_pre_ping": True,
}


db.init_app(app)


# =========================================================
# CSRF対策
# =========================================================

csrf = CSRFProtect(app)


# =========================================================
# ログイン管理
# =========================================================

login_manager = LoginManager()

login_manager.init_app(app)

login_manager.login_view = "login"

login_manager.login_message = "ログインしてください。"


@login_manager.user_loader
def load_user(user_id):

    return db.session.get(
        User,
        int(user_id)
    )


# =========================================================
# 日本時間
# =========================================================

JST = ZoneInfo("Asia/Tokyo")

USER_COLORS = [
    "#0d6efd",
    "#198754",
    "#dc3545",
    "#6f42c1",
    "#fd7e14",
    "#20c997",
    "#d63384",
    "#0dcaf0",
    "#6c757d",
    "#795548",
]

# メール送信関連
# =========================================================
# パスワード再設定用トークン
# =========================================================

PASSWORD_RESET_TOKEN_SALT = "password-reset"
PASSWORD_RESET_TOKEN_MAX_AGE = 60 * 60   # 1時間


def create_password_reset_token(email):

    serializer = URLSafeTimedSerializer(
        app.config["SECRET_KEY"]
    )

    return serializer.dumps(
        email,
        salt=PASSWORD_RESET_TOKEN_SALT
    )


def verify_password_reset_token(token):

    serializer = URLSafeTimedSerializer(
        app.config["SECRET_KEY"]
    )

    try:

        email = serializer.loads(
            token,
            salt=PASSWORD_RESET_TOKEN_SALT,
            max_age=PASSWORD_RESET_TOKEN_MAX_AGE
        )

        return email

    except SignatureExpired:

        return None

    except BadSignature:

        return None
    
# =========================================================
# 新規登録用メール認証トークン
# =========================================================

REGISTRATION_TOKEN_SALT = "email-registration"
REGISTRATION_TOKEN_MAX_AGE = 60 * 60 * 24   # 24時間


def create_registration_token(email):

    serializer = URLSafeTimedSerializer(
        app.config["SECRET_KEY"]
    )

    return serializer.dumps(
        email,
        salt=REGISTRATION_TOKEN_SALT
    )


def verify_registration_token(token):

    serializer = URLSafeTimedSerializer(
        app.config["SECRET_KEY"]
    )

    try:

        email = serializer.loads(
            token,
            salt=REGISTRATION_TOKEN_SALT,
            max_age=REGISTRATION_TOKEN_MAX_AGE
        )

        return email

    except SignatureExpired:

        return None

    except BadSignature:

        return None
    
def send_email(to_address, subject, body):

    msg = EmailMessage()

    msg["Subject"] = subject
    msg["From"] = os.environ["MAIL_FROM"]
    msg["To"] = to_address

    msg.set_content(body)

    with smtplib.SMTP(
        os.environ["MAIL_SERVER"],
        int(os.environ["MAIL_PORT"])
    ) as smtp:

        smtp.starttls()

        smtp.login(
            os.environ["MAIL_USERNAME"],
            os.environ["MAIL_PASSWORD"]
        )

        smtp.send_message(msg)

# =========================================================
# 空き人数計算
# =========================================================

def max_people_during_period(
    room_id,
    start_dt,
    end_dt
):

    reservations = Reservation.query.filter(

        Reservation.room_id == room_id,

        Reservation.status.in_(
            [
                "pending",
                "approved"
            ]
        ),

        Reservation.start_datetime < end_dt,

        Reservation.end_datetime > start_dt

    ).all()


    events = []


    for reservation in reservations:

        overlap_start = max(
            reservation.start_datetime,
            start_dt
        )

        overlap_end = min(
            reservation.end_datetime,
            end_dt
        )


        events.append(
            (
                overlap_start,
                reservation.people
            )
        )

        events.append(
            (
                overlap_end,
                -reservation.people
            )
        )


    # 同じ時刻の場合は、
    # 終了を先に処理してから開始を処理する
    events.sort(
        key=lambda x: (
            x[0],
            0 if x[1] < 0 else 1
        )
    )


    current_people = 0
    max_people = 0


    for _, change in events:

        current_people += change

        if current_people > max_people:
            max_people = current_people


    return max_people


# =========================================================
# トップページ
# =========================================================

@app.route("/")
@login_required
def index():

    if current_user.status != "active":

        logout_user()

        return redirect(
            url_for("login")
        )


    room = db.session.get(
        Room,
        1
    )


    return render_template(
        "index.html",
        room=room
    )


# =========================================================
# 新規利用者登録
# =========================================================

# =========================================================
# 新規利用登録（メール確認）
# =========================================================

@app.route(
    "/register",
    methods=["GET", "POST"]
)
def register():

    if request.method == "POST":

        email = (
            request.form["email"]
            .strip()
            .lower()
        )

        if not email:

            flash(
                "メールアドレスを入力してください。"
            )

            return redirect(
                url_for("register")
            )

        existing = User.query.filter_by(
            email=email
        ).first()

        if existing:

            flash(
                "このメールアドレスは"
                "既に登録されています。"
            )

            return redirect(
                url_for("register")
            )

        token = create_registration_token(
            email
        )

        registration_url = (
            os.environ["APP_BASE_URL"].rstrip("/")
            + url_for(
                "complete_registration",
                token=token
            )
        )

        try:

            send_email(
                email,
                "【実習室予約】利用登録のご案内",
                (
                    "実習室予約システムの利用登録を受け付けました。\n\n"
                    "以下のURLを開いて、登録を完了してください。\n\n"
                    f"{registration_url}\n\n"
                    "このURLの有効期限は24時間です。\n"
                    "心当たりがない場合は、このメールを無視してください。"
                )
            )

        except Exception as e:

            print(
                "Mail send error:",
                e
            )

            flash(
                "確認メールを送信できませんでした。"
                "時間をおいて再度お試しください。"
            )

            return redirect(
                url_for("register")
            )

        flash(
            "確認メールを送信しました。"
            "メールに記載されたURLから"
            "登録を続けてください。"
        )

        return redirect(
            url_for("login")
        )

    return render_template(
        "register.html"
    )

# =========================================================
# 新規利用登録（本登録）
# =========================================================

@app.route(
    "/register/complete/<token>",
    methods=["GET", "POST"]
)
def complete_registration(token):

    email = verify_registration_token(
        token
    )

    if email is None:

        flash(
            "登録用URLが無効、または有効期限が切れています。"
        )

        return redirect(
            url_for("register")
        )

    existing = User.query.filter_by(
        email=email
    ).first()

    if existing:

        flash(
            "このメールアドレスは"
            "既に登録されています。"
        )

        return redirect(
            url_for("login")
        )

    if request.method == "POST":

        name = (
            request.form["name"]
            .strip()
        )

        password = request.form["password"]
        password_confirm = request.form["password_confirm"]

        if not name or not password or not password_confirm:

            flash(
                "すべて入力してください。"
            )

            return redirect(
                url_for(
                    "complete_registration",
                    token=token
                )
            )

        if password != password_confirm:

            flash(
                "確認用パスワードが一致しません。"
            )

            return redirect(
                url_for(
                    "complete_registration",
                    token=token
                )
            )

        user = User(
            name=name,
            email=email,
            role="user",
            status="pending"
        )

        user.set_password(
            password
        )

        db.session.add(
            user
        )

        db.session.commit()

        flash(
            "利用登録を受け付けました。"
            "管理者の承認後にログインできます。"
        )

        return redirect(
            url_for("login")
        )

    return render_template(
        "complete_registration.html",
        email=email
    )

# =========================================================
# ログイン
# =========================================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    if request.method == "POST":

        email = (
            request.form["email"]
            .strip()
            .lower()
        )

        password = request.form["password"]


        user = User.query.filter_by(
            email=email
        ).first()


        if user is None:

            flash(
                "メールアドレスまたは"
                "パスワードが違います。"
            )

            return redirect(
                url_for("login")
            )


        if not user.check_password(password):

            flash(
                "メールアドレスまたは"
                "パスワードが違います。"
            )

            return redirect(
                url_for("login")
            )


        if user.status == "pending":

            flash(
                "現在、管理者の承認待ちです。"
            )

            return redirect(
                url_for("login")
            )


        if user.status != "active":

            flash(
                "このアカウントは利用できません。"
            )

            return redirect(
                url_for("login")
            )


        login_user(
            user
        )


        return redirect(
            url_for("index")
        )


    return render_template(
        "login.html"
    )


# =========================================================
# ログアウト
# =========================================================

@app.route("/logout")
@login_required
def logout():

    logout_user()

    return redirect(
        url_for("login")
    )


# =========================================================
# 管理画面
# =========================================================

@app.route("/admin")
@login_required
def admin_dashboard():

    if not current_user.is_admin:

        flash(
            "管理者のみ利用できます。"
        )

        return redirect(
            url_for("index")
        )


    pending_users = User.query.filter_by(
        status="pending"
    ).all()

    pending_reservations = Reservation.query.filter_by(
        status="pending"
    ).order_by(
        Reservation.batch_id,
        Reservation.start_datetime
    ).all()

    reservation_batches = {}

    for reservation in pending_reservations:
        key = reservation.batch_id or f"single-{reservation.id}"
        if key not in reservation_batches:
            reservation_batches[key] = []

        reservation_batches[key].append(
            reservation
        )

    return render_template(
        "admin.html",
        pending_users=pending_users,
        reservation_batches=reservation_batches,
        JST=JST
    )


# =========================================================
# 利用者承認
# =========================================================

@app.route(
    "/admin/users/<int:user_id>/approve",
    methods=["POST"]
)
@login_required
def approve_user(user_id):

    if not current_user.is_admin:

        flash(
            "管理者のみ利用できます。"
        )

        return redirect(
            url_for("index")
        )


    user = db.session.get(
        User,
        user_id
    )


    if user is None:

        flash(
            "利用者が見つかりません。"
        )

        return redirect(
            url_for("admin_dashboard")
        )


    user.status = "active"

    db.session.commit()


    flash(
        f"{user.name} さんを承認しました。"
    )


    return redirect(
        url_for("admin_dashboard")
    )


# =========================================================
# 空き状況取得API
# =========================================================

@app.route("/api/availability")
@login_required
def availability():

    start_datetime = request.args.get(
        "start"
    )

    end_datetime = request.args.get(
        "end"
    )


    if not start_datetime or not end_datetime:

        return jsonify(
            {
                "error":
                "日時を指定してください。"
            }
        ), 400


    try:

        start_dt = datetime.fromisoformat(
            start_datetime
        ).replace(
            tzinfo=JST
        )

        end_dt = datetime.fromisoformat(
            end_datetime
        ).replace(
            tzinfo=JST
        )


    except ValueError:

        return jsonify(
            {
                "error":
                "日時が不正です。"
            }
        ), 400


    if end_dt <= start_dt:

        return jsonify(
            {
                "error":
                "終了時刻は開始時刻より"
                "後にしてください。"
            }
        ), 400


    room = db.session.get(
        Room,
        1
    )


    used_people = max_people_during_period(
        room.id,
        start_dt,
        end_dt
    )


    available_people = (
        room.capacity
        - used_people
    )


    return jsonify(
        {
            "capacity": room.capacity,
            "used": used_people,
            "available": available_people
        }
    )


# =========================================================
# 利用申請
# =========================================================

@app.route(
    "/reservation/new",
    methods=["GET", "POST"]
)
@login_required
def new_reservation():

    room = db.session.get(
        Room,
        1
    )

    selected_date = request.args.get(
        "date",
        ""
    )

    # -----------------------------------------------------
    # GETの場合は申請画面を表示
    # -----------------------------------------------------

    if request.method != "POST":

        return render_template(
            "reservation.html",
            room=room,
            selected_date=selected_date
        )


    # -----------------------------------------------------
    # フォームから複数日程を取得
    # -----------------------------------------------------

    dates = request.form.getlist(
        "date[]"
    )

    start_times = request.form.getlist(
        "start_time[]"
    )

    end_times = request.form.getlist(
        "end_time[]"
    )

    people_list = request.form.getlist(
        "people[]"
    )


    purpose = request.form.get(
        "purpose",
        ""
    ).strip()


    note = request.form.get(
        "note",
        ""
    ).strip()


    # -----------------------------------------------------
    # 入力数チェック
    # -----------------------------------------------------

    if not dates:

        flash(
            "利用日を入力してください。"
        )

        return redirect(
            url_for("new_reservation")
        )


    if not (
        len(dates)
        == len(start_times)
        == len(end_times)
        == len(people_list)
    ):

        flash(
            "日程の入力内容が不正です。"
        )

        return redirect(
            url_for("new_reservation")
        )


    # -----------------------------------------------------
    # 各日程をPythonの日時に変換
    # -----------------------------------------------------

    schedules = []
    seen_schedules = set()

    for (
        date_value,
        start_value,
        end_value,
        people_value
    ) in zip(
        dates,
        start_times,
        end_times,
        people_list
    ):

        try:

            start_dt = datetime.fromisoformat(
                date_value
                + "T"
                + start_value
            ).replace(
                tzinfo=JST
            )


            end_dt = datetime.fromisoformat(
                date_value
                + "T"
                + end_value
            ).replace(
                tzinfo=JST
            )


            people = int(
                people_value
            )


        except ValueError:

            flash(
                "日時または利用人数を"
                "確認してください。"
            )

            return redirect(
                url_for("new_reservation")
            )


        # -------------------------------------------------
        # 開始・終了時刻チェック
        # -------------------------------------------------

        if end_dt <= start_dt:

            flash(
                f"{date_value} の終了時刻は"
                f"開始時刻より後にしてください。"
            )

            return redirect(
                url_for("new_reservation")
            )

        if start_dt.date() < date.today():
            flash(
                f"{date_value} は過去の日付のため予約できません。"
            )
            return redirect(
                url_for("new_reservation")
            )

        # -------------------------------------------------
        # 人数チェック
        # -------------------------------------------------

        if people < 1 or people > room.capacity:

            flash(
                f"{date_value} の利用人数は"
                f"1～{room.capacity}人で"
                f"入力してください。"
            )

            return redirect(
                url_for("new_reservation")
            )

        schedule_key = (
            start_dt,
            end_dt
        )

        if schedule_key in seen_schedules:
            flash(
                f"{date_value} {start_value}～{end_value} が"
                f"重複しています。"
            )
            return redirect(
                url_for("new_reservation")
            )

        seen_schedules.add(schedule_key)

        for existing_schedule in schedules:
            # 同じ日の予約だけ確認
            if (
                existing_schedule["start"].date()
                == start_dt.date()
            ):
                # 時間帯が重なっているか
                if (
                    existing_schedule["start"] < end_dt
                    and
                    existing_schedule["end"] > start_dt
                ):
                    flash(
                        f"{date_value} の日程で"
                        f"時間帯が重複しています。"
                    )

                    return redirect(
                        url_for("new_reservation")
                    )
        
        schedules.append(
            {
                "start": start_dt,
                "end": end_dt,
                "people": people
            }
        )


    # -----------------------------------------------------
    # 一括申請を識別するID
    # -----------------------------------------------------

    batch_id = str(
        uuid.uuid4()
    )


    # =====================================================
    # ここからDBトランザクション
    # =====================================================

    try:

        # -------------------------------------------------
        # 部屋単位で予約処理をロック
        #
        # 同時に複数ユーザーが申請しても、
        # 1件ずつ順番に人数チェックする
        # -------------------------------------------------

        db.session.execute(
            text(
                "SELECT "
                "pg_advisory_xact_lock(:room_id)"
            ),
            {
                "room_id": room.id
            }
        )


        # -------------------------------------------------
        # ロック取得後に全日程を再チェック
        # -------------------------------------------------

        for schedule in schedules:

            used_people = max_people_during_period(
                room.id,
                schedule["start"],
                schedule["end"]
            )


            available_people = (
                room.capacity
                - used_people
            )


            if (
                schedule["people"]
                > available_people
            ):

                local_date = (
                    schedule["start"]
                    .strftime("%Y/%m/%d")
                )


                # トランザクションを終了し、
                # advisory lockも解放
                db.session.rollback()


                flash(
                    f"{local_date} のこの時間帯は"
                    f"空きが {available_people}人です。"
                    f"一括申請は登録されませんでした。"
                )


                return redirect(
                    url_for("new_reservation")
                )


        # -------------------------------------------------
        # 全日程が申請可能ならまとめて登録
        # -------------------------------------------------

        for schedule in schedules:

            reservation = Reservation(

                room_id=room.id,

                user_id=current_user.id,

                start_datetime=
                    schedule["start"],

                end_datetime=
                    schedule["end"],

                people=
                    schedule["people"],

                purpose=purpose,

                note=note,

                batch_id=batch_id,

                status="pending"
            )


            db.session.add(
                reservation
            )


        # -------------------------------------------------
        # 一括確定
        # -------------------------------------------------

        db.session.commit()

        admin_url = (
            os.environ["APP_BASE_URL"].rstrip("/")
            + "/admin"
        )

        try:
            admin_users = User.query.filter_by(
                role="admin",
                status="active"
            ).all()

            for admin in admin_users:
                send_email(
                    admin.email,
                    "【実習室予約】新しい利用申請があります",
                    (
                        f"{current_user.name} さんから"
                        f"{len(schedules)}件の利用申請がありました。\n\n"
                        f"利用目的：{purpose or '－'}\n"
                        f"備考：{note or '－'}\n\n"
                        "以下のURLから管理画面を開けます。\n"
                        f"{admin_url}"
                    )
                )

        except Exception as e:
            print(
                "Mail send error:",
                e
            )


    except Exception as e:

        # -------------------------------------------------
        # 途中で何か失敗した場合はすべて取消
        # -------------------------------------------------

        db.session.rollback()


        # 開発中なのでターミナルに詳細を表示
        print(
            "Reservation error:",
            e
        )


        flash(
            "申請処理中にエラーが発生しました。"
        )


        return redirect(
            url_for("new_reservation")
        )


    # -----------------------------------------------------
    # 正常終了
    # -----------------------------------------------------

    if len(schedules) == 1:
        flash(
            "1件の利用申請を登録しました。"
        )
    else:
        flash(
            f"{len(schedules)}件の利用申請を"
            "まとめて登録しました。"
        )


    return redirect(
        url_for("index")
    )


@app.route(
    "/admin/reservations/<int:reservation_id>/approve",
    methods=["POST"]
)
@login_required
def approve_reservation(reservation_id):

    if not current_user.is_admin:
        flash("管理者のみ利用できます。")
        return redirect(url_for("index"))

    reservation = db.session.get(
        Reservation,
        reservation_id
    )

    if reservation is None:
        flash("予約申請が見つかりません。")
        return redirect(
            url_for("admin_dashboard")
        )

    if reservation.status != "pending":
        flash("この予約申請はすでに処理されています。")
        return redirect(
            url_for("admin_dashboard")
        )

    reservation.status = "approved"
    reservation.approved_at = datetime.now(JST)
    reservation.approved_by = current_user.id

    db.session.commit()

    try:
        send_email(
            reservation.user.email,
            "【実習室予約】利用申請が承認されました",
            (
                f"{reservation.user.name} さん\n\n"
                "以下の利用申請が承認されました。\n\n"
                f"利用日：{reservation.start_datetime.astimezone(JST).strftime('%Y/%m/%d')}\n"
                f"時間：{reservation.start_datetime.astimezone(JST).strftime('%H:%M')}"
                f" ～ {reservation.end_datetime.astimezone(JST).strftime('%H:%M')}\n"
                f"利用人数：{reservation.people}人\n"
                f"利用目的：{reservation.purpose or '－'}\n"
            )
        )

    except Exception as e:
        print(
            "Mail send error:",
            e
        )

    flash("予約申請を承認しました。")

    return redirect(
        url_for("admin_dashboard")
    )


@app.route(
    "/admin/reservations/<int:reservation_id>/reject",
    methods=["POST"]
)
@login_required
def reject_reservation(reservation_id):

    if not current_user.is_admin:
        flash("管理者のみ利用できます。")
        return redirect(url_for("index"))

    reservation = db.session.get(
        Reservation,
        reservation_id
    )

    if reservation is None:
        flash("予約申請が見つかりません。")
        return redirect(
            url_for("admin_dashboard")
        )

    if reservation.status != "pending":
        flash("この予約申請はすでに処理されています。")
        return redirect(
            url_for("admin_dashboard")
        )

    reservation.status = "rejected"
    reservation.rejected_at = datetime.now(JST)
    reservation.rejected_by = current_user.id

    db.session.commit()

    flash(
        "予約申請を却下しました。"
        "確保されていた人数枠は解放されました。"
    )

    return redirect(
        url_for("admin_dashboard")
    )

@app.route("/reservations")
@login_required
def my_reservations():

    reservations = Reservation.query.filter_by(
        user_id=current_user.id
    ).order_by(
        Reservation.start_datetime.desc()
    ).all()

    return render_template(
        "my_reservations.html",
        reservations=reservations,
        JST=JST
    )

@app.route(
    "/reservations/<int:reservation_id>/cancel",
    methods=["POST"]
)
@login_required
def cancel_reservation(reservation_id):

    reservation = db.session.get(
        Reservation,
        reservation_id
    )

    if reservation is None:
        flash("予約が見つかりません。")
        return redirect(
            url_for("my_reservations")
        )

    # 自分の予約以外はキャンセルできない
    if reservation.user_id != current_user.id:
        flash("この予約はキャンセルできません。")
        return redirect(
            url_for("my_reservations")
        )

    # pending または approved のみキャンセル可能
    if reservation.status not in [
        "pending",
        "approved"
    ]:
        flash("この予約はキャンセルできません。")
        return redirect(
            url_for("my_reservations")
        )

    reservation.status = "cancelled"

    db.session.commit()

    flash(
        "予約をキャンセルしました。"
        "確保されていた人数枠を解放しました。"
    )

    return redirect(
        url_for("my_reservations")
    )

@app.route("/api/calendar-events")
@login_required
def calendar_events():

    reservations = Reservation.query.filter(
        Reservation.status.in_([
            "pending",
            "approved"
        ])
    ).order_by(
        Reservation.start_datetime
    ).all()

    events = []

    for reservation in reservations:
        if reservation.status == "approved":
            status_text = "承認済"
        else:
            status_text = "申請中"

        is_own = (
            reservation.user_id
            == current_user.id
        )

        details_visible = (
            current_user.is_admin
            or is_own
        )

        color = USER_COLORS[
            (reservation.user_id - 1)
            % len(USER_COLORS)
        ]

        events.append({
            "id": reservation.id,

            "title": (
                f"{reservation.people}人 "
                f"({status_text})"
            ),

            "start":
                reservation.start_datetime.isoformat(),

            "end":
                reservation.end_datetime.isoformat(),

            "status":
                reservation.status,

            "people":
                reservation.people,

            "user_name": (
                reservation.user.name
                if details_visible
                else "他の利用者"
            ),

            "purpose": (
                reservation.purpose or ""
                if details_visible
                else ""
            ),

            "details_visible":
                details_visible,

            "backgroundColor":
                color,

            "borderColor":
                color,
        })

    return jsonify(events)

@app.route(
    "/admin/reservations/batch/<batch_id>/approve",
    methods=["POST"]
)
@login_required
def approve_reservation_batch(batch_id):

    if not current_user.is_admin:
        flash("管理者のみ利用できます。")
        return redirect(url_for("index"))

    reservations = Reservation.query.filter_by(
        batch_id=batch_id,
        status="pending"
    ).all()

    if not reservations:
        flash("承認待ちの申請が見つかりません。")
        return redirect(
            url_for("admin_dashboard")
        )

    approved_at = datetime.now(JST)
    for reservation in reservations:
        reservation.status = "approved"
        reservation.approved_at = approved_at
        reservation.approved_by = current_user.id

    db.session.commit()

    try:
        user = reservations[0].user

        schedule_lines = []

        for reservation in reservations:
            schedule_lines.append(
            (
                f"{reservation.start_datetime.astimezone(JST).strftime('%Y/%m/%d')} "
                f"{reservation.start_datetime.astimezone(JST).strftime('%H:%M')}"
                f" ～ "
                f"{reservation.end_datetime.astimezone(JST).strftime('%H:%M')}"
                f"　{reservation.people}人"
            )
        )
        schedule_text = "\n".join(schedule_lines)

        send_email(
            user.email,
            "【実習室予約】利用申請が承認されました",
            (
                f"{user.name} さん\n\n"
                "以下の利用申請が承認されました。\n\n"
                f"{schedule_text}\n\n"
                f"利用目的：{reservations[0].purpose or '－'}\n"
                f"備考：{reservations[0].note or '－'}\n"
            )
        )

    except Exception as e:
        print(
            "Mail send error:",
            e
        )

    if len(reservations) == 1:
        flash(
            "1件の利用申請を承認しました。"
        )
    else:
        flash(
            f"{len(reservations)}件の利用申請を"
            "まとめて承認しました。"
        )

    return redirect(
        url_for("admin_dashboard")
    )


@app.route(
    "/admin/reservations/batch/<batch_id>/reject",
    methods=["POST"]
)
@login_required
def reject_reservation_batch(batch_id):

    if not current_user.is_admin:
        flash("管理者のみ利用できます。")
        return redirect(url_for("index"))

    reservations = Reservation.query.filter_by(
        batch_id=batch_id,
        status="pending"
    ).all()

    if not reservations:
        flash("承認待ちの申請が見つかりません。")
        return redirect(
            url_for("admin_dashboard")
        )

    rejected_at = datetime.now(JST)

    for reservation in reservations:
        reservation.status = "rejected"
        reservation.rejected_at = rejected_at
        reservation.rejected_by = current_user.id

    db.session.commit()

    if len(reservations) == 1:
        flash(
            "1件の利用申請を却下しました。"
        )
    else:
        flash(
            f"{len(reservations)}件の利用申請を"
            "まとめて却下しました。"
        )

    return redirect(
        url_for("admin_dashboard")
    )

@app.route(
    "/profile",
    methods=["GET", "POST"]
)
@login_required
def profile():

    if request.method == "POST":

        name = request.form.get(
            "name",
            ""
        ).strip()

        if not name:

            flash(
                "氏名を入力してください。"
            )

            return redirect(
                url_for("profile")
            )

        current_user.name = name

        db.session.commit()

        flash(
            "氏名を変更しました。"
        )

        return redirect(
            url_for("profile")
        )

    return render_template(
        "profile.html"
    )

@app.route("/admin/users")
@login_required
def admin_users():

    if not current_user.is_admin:
        flash("管理者のみ利用できます。")
        return redirect(url_for("index"))

    users = User.query.order_by(
        User.name
    ).all()

    return render_template(
        "admin_users.html",
        users=users
    )

@app.route(
    "/admin/users/<int:user_id>/deactivate",
    methods=["POST"]
)
@login_required
def deactivate_user(user_id):

    if not current_user.is_admin:
        flash("管理者のみ利用できます。")
        return redirect(url_for("index"))

    user = db.session.get(User, user_id)

    if user is None:
        flash("利用者が見つかりません。")
        return redirect(url_for("admin_users"))

    if user.is_admin:
        flash("管理者は無効化できません。")
        return redirect(url_for("admin_users"))

    user.status = "inactive"
    db.session.commit()

    flash(f"{user.name} さんを利用停止にしました。")

    return redirect(url_for("admin_users"))


@app.route(
    "/admin/users/<int:user_id>/activate",
    methods=["POST"]
)
@login_required
def activate_user(user_id):

    if not current_user.is_admin:
        flash("管理者のみ利用できます。")
        return redirect(url_for("index"))

    user = db.session.get(User, user_id)

    if user is None:
        flash("利用者が見つかりません。")
        return redirect(url_for("admin_users"))

    user.status = "active"
    db.session.commit()

    flash(f"{user.name} さんを利用可能にしました。")

    return redirect(url_for("admin_users"))

@app.route("/admin/reservations")
@login_required
def admin_reservations():

    if not current_user.is_admin:
        flash("管理者のみ利用できます。")
        return redirect(url_for("index"))

    reservations = Reservation.query.order_by(
        Reservation.start_datetime.desc()
    ).all()

    users = User.query.all()

    user_names = {
        user.id: user.name
        for user in users
    }

    return render_template(
        "admin_reservations.html",
        reservations=reservations,
        JST=JST,
        user_names=user_names
    )

@app.route(
    "/forgot-password",
    methods=["GET", "POST"]
)
def forgot_password():

    if request.method == "POST":

        email = request.form.get(
            "email",
            ""
        ).strip()

        user = User.query.filter_by(
            email=email
        ).first()

        # 存在するメールアドレスの場合だけ送信
        if user is not None:

            token = create_password_reset_token(
                email
            )

            reset_url = (
                os.environ["APP_BASE_URL"].rstrip("/")
                + url_for(
                    "reset_password",
                    token=token
                )
            )

            try:

                send_email(
                    email,
                    "パスワード再設定",
                    (
                        "パスワードを再設定するには、"
                        "以下のURLを開いてください。\n\n"
                        f"{reset_url}\n\n"
                        "このURLの有効期限は1時間です。"
                    )
                )

            except Exception as e:

                print(
                    "Password reset email error:",
                    e
                )

        # メールアドレスの存在有無は表示しない
        flash(
            "入力されたメールアドレスが"
            "登録されている場合、"
            "パスワード再設定用メールを送信しました。"
        )

        return redirect(
            url_for("login")
        )

    return render_template(
        "forgot_password.html"
    )

@app.route(
    "/reset-password/<token>",
    methods=["GET", "POST"]
)
def reset_password(token):

    email = verify_password_reset_token(
        token
    )

    if email is None:

        flash(
            "パスワード再設定用URLが"
            "無効または期限切れです。"
        )

        return redirect(
            url_for("forgot_password")
        )

    user = User.query.filter_by(
        email=email
    ).first()

    if user is None:

        flash(
            "利用者情報が見つかりません。"
        )

        return redirect(
            url_for("login")
        )

    if request.method == "POST":

        password = request.form.get(
            "password",
            ""
        )

        password_confirm = request.form.get(
            "password_confirm",
            ""
        )

        if not password:

            flash(
                "新しいパスワードを"
                "入力してください。"
            )

            return render_template(
                "reset_password.html",
                token=token
            )

        if password != password_confirm:

            flash(
                "確認用パスワードが"
                "一致しません。"
            )

            return render_template(
                "reset_password.html",
                token=token
            )

        user.set_password(
            password
        )

        db.session.commit()

        flash(
            "パスワードを変更しました。"
            "新しいパスワードで"
            "ログインしてください。"
        )

        return redirect(
            url_for("login")
        )

    return render_template(
        "reset_password.html",
        token=token
    )

# =========================================================
# アプリ起動
# =========================================================

if __name__ == "__main__":

    with app.app_context():

        # テーブルが存在しない場合のみ作成
        db.create_all()


        # -------------------------------------------------
        # 部屋データを初回のみ作成
        # -------------------------------------------------

        room = db.session.get(
            Room,
            1
        )


        if room is None:

            room = Room(
                id=1,
                name=(
                    "14号館3階 "
                    "電子情報計算機実習室"
                ),
                capacity=20
            )


            db.session.add(
                room
            )

            db.session.commit()


            print(
                "Room created."
            )


    app.run(
        debug=True
    )