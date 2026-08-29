from getpass import getpass

from app import app
from models import db, User


with app.app_context():

    name = input("管理者氏名: ")
    email = input("メールアドレス: ")
    password = getpass("パスワード: ")

    existing = User.query.filter_by(email=email).first()

    if existing:
        print("このメールアドレスは既に登録されています。")
        exit()

    user = User(
        name=name,
        email=email,
        role="admin",
        status="active"
    )

    user.set_password(password)

    db.session.add(user)
    db.session.commit()

    print("管理者を作成しました。")
    