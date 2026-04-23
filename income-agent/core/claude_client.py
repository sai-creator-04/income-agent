import json
import requests
import os
import time
import logging

logger = logging.getLogger(__name__)

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-lite-latest:generateContent"
MAX_RETRIES = 3
RETRY_DELAY = 2


class ClaudeClient:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not set in environment")

    def ask(self, system: str, user: str, max_tokens: int = 1024) -> str:
        payload = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"parts": [{"text": user}]}],
            "generationConfig": {"maxOutputTokens": max_tokens}
        }
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = requests.post(
                    f"{GEMINI_URL}?key={self.api_key}",
                    json=payload,
                    timeout=30
                )
                resp.raise_for_status()
                data = resp.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"]
                logger.info(f"Gemini responded ({len(text)} chars)")
                return text.strip()
            except requests.exceptions.HTTPError as e:
                status = e.response.status_code if e.response else 0
                if status == 429:
                    time.sleep(RETRY_DELAY * attempt)
                elif status >= 500:
                    time.sleep(RETRY_DELAY)
                else:
                    logger.error(f"Gemini HTTP error {status}: {e}")
                    raise
            except Exception as e:
                logger.warning(f"Attempt {attempt} failed: {e}")
                if attempt == MAX_RETRIES:
                    raise
                time.sleep(RETRY_DELAY)
        raise RuntimeError(f"Gemini API failed after {MAX_RETRIES} attempts")