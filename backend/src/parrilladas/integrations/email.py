"""Small SMTP adapter used by the durable notification outbox."""

import smtplib
import ssl
from email.message import EmailMessage


class EmailSendError(RuntimeError):
    category = "email_delivery"


class SmtpEmailClient:
    def send(
        self,
        *,
        host: str,
        port: int,
        username: str | None,
        password: str | None,
        sender: str | None,
        recipient: str,
        subject: str,
        body: str,
    ) -> str:
        if not username or not password:
            raise EmailSendError("Email SMTP credentials are not configured")
        message = EmailMessage()
        message["From"] = sender or username
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(body)
        try:
            with smtplib.SMTP(host, port, timeout=15) as smtp:
                smtp.starttls(context=ssl.create_default_context())
                smtp.login(username, password)
                smtp.send_message(message)
        except (OSError, smtplib.SMTPException) as error:
            raise EmailSendError("SMTP delivery failed") from error
        return f"smtp:{recipient}"
