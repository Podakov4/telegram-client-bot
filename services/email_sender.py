import smtplib
from email.message import EmailMessage

from config import (
    SMTP_ENABLED,
    SMTP_HOST,
    SMTP_PORT,
    SMTP_USERNAME,
    SMTP_PASSWORD,
    SMTP_FROM_EMAIL,
    SMTP_FROM_NAME,
    SMTP_USE_TLS,
    SMTP_USE_SSL,
)


class EmailSenderError(Exception):
    pass


def build_login_code_email(to_email: str, code: str) -> EmailMessage:
    message = EmailMessage()

    from_display = SMTP_FROM_EMAIL
    if SMTP_FROM_NAME:
        from_display = f"{SMTP_FROM_NAME} <{SMTP_FROM_EMAIL}>"

    message["Subject"] = "Код входа в Freeth"
    message["From"] = from_display
    message["To"] = to_email

    text_body = (
        f"Ваш код входа в Freeth: {code}\n\n"
        "Код одноразовый. Никому его не передавайте.\n"
        "Если вы не запрашивали вход, просто проигнорируйте это письмо."
    )

    html_body = f"""
    <html>
      <body style="font-family: Arial, sans-serif; line-height: 1.5;">
        <h2>Вход в Freeth</h2>
        <p>Ваш одноразовый код:</p>
        <p style="font-size: 28px; font-weight: bold; letter-spacing: 4px;">{code}</p>
        <p>Никому не передавайте этот код.</p>
        <p>Если вы не запрашивали вход, просто проигнорируйте это письмо.</p>
      </body>
    </html>
    """

    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")
    return message


def send_email_message(message: EmailMessage) -> None:
    if not SMTP_ENABLED:
        raise EmailSenderError("SMTP is disabled")

    if not SMTP_HOST or not SMTP_PORT or not SMTP_FROM_EMAIL:
        raise EmailSenderError("SMTP config is incomplete")

    try:
        if SMTP_USE_SSL:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=20) as server:
                if SMTP_USERNAME:
                    server.login(SMTP_USERNAME, SMTP_PASSWORD or "")
                server.send_message(message)
            return

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
            if SMTP_USE_TLS:
                server.starttls()
            if SMTP_USERNAME:
                server.login(SMTP_USERNAME, SMTP_PASSWORD or "")
            server.send_message(message)
    except Exception as exc:
        raise EmailSenderError(f"Failed to send email: {exc}") from exc


def send_login_code_email(to_email: str, code: str) -> None:
    message = build_login_code_email(to_email=to_email, code=code)
    send_email_message(message)