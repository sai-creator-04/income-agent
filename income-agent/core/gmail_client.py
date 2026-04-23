"""
Gmail SMTP client for sending buyer support replies.
Uses App Passwords (no OAuth dance needed).
Setup: Google Account → Security → 2FA on → App Passwords → generate one.
"""
import smtplib
import ssl
import os
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

logger = logging.getLogger(__name__)

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465


class GmailClient:
    def __init__(self, email: str = None, app_password: str = None):
        self.email = email or os.environ.get("GMAIL_ADDRESS")
        self.app_password = app_password or os.environ.get("GMAIL_APP_PASSWORD")
        if not self.email:
            raise ValueError("GMAIL_ADDRESS not set")
        if not self.app_password:
            raise ValueError("GMAIL_APP_PASSWORD not set")

    def send(
        self,
        to: str,
        subject: str,
        body: str,
        reply_to_message_id: Optional[str] = None,
    ) -> bool:
        """
        Send an email via Gmail SMTP.
        reply_to_message_id threads the reply correctly in Gmail.
        """
        msg = MIMEMultipart("alternative")
        msg["From"] = self.email
        msg["To"] = to
        msg["Subject"] = subject

        if reply_to_message_id:
            msg["In-Reply-To"] = reply_to_message_id
            msg["References"] = reply_to_message_id

        msg.attach(MIMEText(body, "plain"))

        context = ssl.create_default_context()
        try:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context) as server:
                server.login(self.email, self.app_password)
                server.sendmail(self.email, to, msg.as_string())
            logger.info(f"Email sent to {to} — subject: {subject}")
            return True
        except smtplib.SMTPAuthenticationError:
            logger.error("Gmail auth failed — check your App Password")
            return False
        except smtplib.SMTPException as e:
            logger.error(f"SMTP error: {e}")
            return False
        except Exception as e:
            logger.error(f"Email send failed: {e}")
            return False
