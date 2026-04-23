"""
Telegram bot client.
Sends agent outputs (Reddit drafts, DM lists, alerts) to you via Telegram.
Free, instant, works on any phone.
"""
import requests
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


class TelegramClient:
    def __init__(self, token: str = None, chat_id: str = None):
        self.token = token or os.environ.get("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID")
        if not self.token:
            raise ValueError("TELEGRAM_BOT_TOKEN not set")
        if not self.chat_id:
            raise ValueError("TELEGRAM_CHAT_ID not set")

    def _url(self, method: str) -> str:
        return TELEGRAM_API.format(token=self.token, method=method)

    def send(self, message: str, parse_mode: str = "Markdown") -> bool:
        """Send a message to your Telegram chat. Returns True on success."""
        if len(message) > 4096:
            return self._send_long(message, parse_mode)

        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": parse_mode,
        }
        try:
            resp = requests.post(self._url("sendMessage"), json=payload, timeout=10)
            resp.raise_for_status()
            logger.info(f"Telegram message sent ({len(message)} chars)")
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Telegram send failed: {e}")
            return False

    def _send_long(self, message: str, parse_mode: str) -> bool:
        """Split messages over 4096 chars into chunks."""
        chunks = [message[i:i+4000] for i in range(0, len(message), 4000)]
        success = True
        for i, chunk in enumerate(chunks, 1):
            header = f"*Part {i}/{len(chunks)}*\n\n" if len(chunks) > 1 else ""
            success = self.send(header + chunk, parse_mode) and success
        return success

    def alert(self, title: str, body: str) -> bool:
        """Send a structured alert with bold title."""
        return self.send(f"*{title}*\n\n{body}")

    def send_draft(self, label: str, content: str, instructions: str = "") -> bool:
        """Send a draft (Reddit post, DM, etc.) with copy instructions."""
        msg = (
            f"*{label}*\n"
            f"{'─' * 30}\n"
            f"{content}\n"
            f"{'─' * 30}\n"
        )
        if instructions:
            msg += f"\n_{instructions}_"
        return self.send(msg)
