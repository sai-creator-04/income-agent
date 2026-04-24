"""
Agent 2: Content Agent
──────────────────────
Trigger : Cron every Sunday 09:00
Action  : Gemini writes 7 trading psychology posts → saves to posts_ready.json
          → sends all posts to Telegram → Make.com picks them up and posts to Twitter
Cost    : ~$0.02/week
"""
import logging
import os
import re
import json
from datetime import date
from typing import List
from core.claude_client import ClaudeClient
from core.buffer_client import BufferClient
from core.telegram_client import TelegramClient

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a social media content writer for a trading psychology brand.

Write exactly 7 Twitter/X posts about trading psychology — one per line, separated by blank lines.
Each post must:
- Be under 250 characters
- Give one actionable trading psychology tip or insight
- End with: "Full checklist -> [LINK]"
- Feel like advice from a real trader who's been through losses
- Use plain language, no jargon, no emojis

TOPICS to rotate through (use a different one each post):
1. Managing revenge trading urges
2. Position sizing discipline
3. Journaling your trades
4. Pre-market mental preparation
5. Cutting losses quickly
6. The psychology of a winning streak
7. Dealing with a losing day

Output ONLY the 7 posts, numbered 1-7. Nothing else."""

TWEET_LINK = "https://gum.co/tradingpsych"
HASHTAGS = "#tradingpsychology #daytrading #forextrader #stockmarket #retailtrader"


class ContentAgent:
    def __init__(self, claude=None, buffer=None, telegram=None, gumroad_link=None):
        self.claude = claude or ClaudeClient()
        self.buffer = buffer or BufferClient()
        self.telegram = telegram or TelegramClient()
        self.gumroad_link = gumroad_link or os.environ.get("GUMROAD_LINK", TWEET_LINK)

    def generate_posts(self) -> List[str]:
        logger.info("Generating weekly content batch...")
        raw = self.claude.ask(
            SYSTEM_PROMPT,
            f"Generate 7 posts for the week of {date.today().strftime('%B %d, %Y')}.",
            max_tokens=1200,
        )
        posts = self._parse_posts(raw)
        # Replace link placeholder and add hashtags
        final = []
        for p in posts:
            p = p.replace("[LINK]", self.gumroad_link)
            p = p.replace("-> ", "→ ")
            if HASHTAGS not in p:
                p = p + f"\n{HASHTAGS}"
            final.append(p)
        logger.info(f"Generated {len(final)} posts")
        return final

    def _parse_posts(self, raw: str) -> List[str]:
        raw = raw.strip()
        posts = []

        is_numbered = bool(re.search(r"(?m)^\d+[\.\)]\s+", raw))

        if is_numbered:
            chunks = re.split(r"(?m)^\d+[\.\)]\s+", raw)
            for chunk in chunks:
                text = " ".join(chunk.split())
                if len(text) > 5:
                    posts.append(text)
            if posts:
                return posts[:7]

        blocks = re.split(r"\n{2,}", raw)
        for block in blocks:
            block = re.sub(r"^\d+[\.\)]\s*", "", " ".join(block.split()))
            if len(block) > 5:
                posts.append(block)
        return posts[:7]

    def _save_posts_for_makecom(self, posts: List[str]) -> None:
        """Save posts to JSON file so Make.com can read and post them to Twitter."""
        payload = {
            "date": date.today().isoformat(),
            "week": date.today().strftime("%Y-W%U"),
            "posts": posts,
            "count": len(posts)
        }
        try:
            with open("posts_ready.json", "w") as f:
                json.dump(payload, f, indent=2)
            logger.info(f"Saved {len(posts)} posts to posts_ready.json")
        except Exception as e:
            logger.error(f"Failed to save posts: {e}")

    def run(self) -> dict:
        try:
            posts = self.generate_posts()
        except Exception as e:
            logger.error(f"Content generation failed: {e}")
            self.telegram.alert("Content Agent Error", f"Failed to generate posts: {e}")
            return {"status": "error", "error": str(e)}

        if not posts:
            logger.error("No posts generated — aborting")
            self.telegram.alert("Content Agent", "Generated 0 posts — check prompt")
            return {"status": "empty"}

        # Save for Make.com to pick up
        self._save_posts_for_makecom(posts)

        # Send all posts to Telegram so you can see them
        posts_preview = "\n\n".join(
            f"*Post {i+1}:*\n{p}" for i, p in enumerate(posts)
        )
        self.telegram.send(
            f"*7 Twitter posts generated — week of {date.today().strftime('%b %d')}*\n\n"
            f"{posts_preview}\n\n"
            f"_These will be posted to Twitter via Make.com automatically._"
        )

        logger.info(f"Content agent done — {len(posts)} posts ready")
        return {
            "status": "ready",
            "posts": posts,
            "count": len(posts)
        }