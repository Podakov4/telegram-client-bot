import json
import logging
import urllib.error
import urllib.request

from config import (
    EMAIL_PROVIDER,
    RESEND_API_KEY,
    RESEND_ENABLED,
    RESEND_FROM_EMAIL,
    RESEND_FROM_NAME,
)

logger = logging.getLogger(__name__)


class EmailSenderError(Exception):
    pass


def _build_subject() -> str:
    return "Код входа в Freeth"


def _build_text_body(code: str) -> str:
    return (
        f"Ваш код входа в Freeth: {code}\n\n"
        "Код одноразовый. Никому его не передавайте.\n"
        "Если вы не запрашивали вход, просто проигнорируйте это письмо."
    )


def _build_html_body(code: str) -> str:
    return f"""
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


def _send_via_resend(to_email: str, code: str) -> None:
    if not RESEND_ENABLED:
        raise EmailSenderError("Resend is disabled")

    if not RESEND_API_KEY:
        raise EmailSenderError("RESEND_API_KEY is empty")

    if not RESEND_FROM_EMAIL:
        raise EmailSenderError("RESEND_FROM_EMAIL is empty")

    from_value = RESEND_FROM_EMAIL
    if RESEND_FROM_NAME:
        from_value = f"{RESEND_FROM_NAME} <{RESEND_FROM_EMAIL}>"

    payload = {
        "from": from_value,
        "to": [to_email],
        "subject": _build_subject(),
        "text": _build_text_body(code),
        "html": _build_html_body(code),
    }

    req = urllib.request.Request(
        url="https://api.resend.com/emails",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            body = response.read().decode("utf-8", errors="replace")
            logger.info("Resend send success: %s", body)
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise EmailSenderError(
            f"Resend HTTP {exc.code}: {error_body}"
        ) from exc
    except Exception as exc:
        raise EmailSenderError(f"Resend request failed: {exc}") from exc


def send_login_code_email(to_email: str, code: str) -> None:
    if EMAIL_PROVIDER == "resend":
        _send_via_resend(to_email=to_email, code=code)
        return

    raise EmailSenderError(f"Unsupported EMAIL_PROVIDER: {EMAIL_PROVIDER}")