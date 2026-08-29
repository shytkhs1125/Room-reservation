from app import send_email

send_email(
    "shinya1125@gmail.com",
    "Room Reservation メールテスト",
    "Gmail SMTP からのテストメールです。"
)

print("メール送信処理が完了しました。")
