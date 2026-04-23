"""
Agent 2: Content Agent
──────────────────────
Trigger : Cron every Sunday 09:00
Action  : Claude writes 7 trading psychology posts → Buffer queues them Mon–Sun
Cost    : ~$0.02/week
"""
import logging
import os
import re
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
- End with: "Full checklist → [LINK]"
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

Output ONLY the 7 posts, numbered 1–7. Nothing else."""

TWEET_LINK = "https://gum.co/tradingpsych"


class ContentAgent:
    def __init__(
        self,
        claude: ClaudeClient = None,
        buffer: BufferClient = None,
        telegram: TelegramClient = None,
        gumroad_link: str = None,
    ):
        self.claude = claude or ClaudeClient()
        self.buffer = buffer or BufferClient()
        self.telegram = telegram or TelegramClient()
        self.gumroad_link = gumroad_link or os.environ.get("GUMROAD_LINK", TWEET_LINK)

    def generate_posts(self) -> List[str]:
        """Ask Claude to generate 7 posts. Returns cleaned list."""
        logger.info("Generating weekly content batch...")
        raw = self.claude.ask(
            SYSTEM_PROMPT,
            f"Generate 7 posts for the week of {date.today().strftime('%B %d, %Y')}.",
            max_tokens=1200,
        )
        posts = self._parse_posts(raw)
        posts = [p.replace("[LINK]", self.gumroad_link) for p in posts]
        logger.info(f"Generated {len(posts)} posts")
        return posts

    def _parse_posts(self, raw: str) -> List[str]:
        """
        Parse numbered posts from Claude output.
        Handles: "1. text", "1) text", blank-line separated blocks.
        """
        raw = raw.strip()
        posts = []

        # Detect if input is numbered format (has "1. " or "1) " patterns)
        is_numbered = bool(re.search(r"(?m)^\d+[\.\)]\s+", raw))

        if is_numbered:
            chunks = re.split(r"(?m)^\d+[\.\)]\s+", raw)
            for chunk in chunks:
                text = " ".join(chunk.split())
                if len(text) > 5:
                    posts.append(text)
            if posts:
                return posts[:7]

        # Fallback: blank-line separated blocks
        blocks = re.split(r"\n{2,}", raw)
        for block in blocks:
            block = re.sub(r"^\d+[\.\)]\s*", "", " ".join(block.split()))
            if len(block) > 5:
                posts.append(block)
        return posts[:7]

    def run(self) -> dict:
        """
        Full weekly run: generate → schedule → notify.
        Called every Sunday by the scheduler.
        """
        try:
            posts = self.generate_posts()
        except Exception as e:
            logger.error(f"Content generation failed: {e}")
            self.telegram.alert("Content Agent Error", f"Failed to generate posts: {e}")
            return {"status": "error", "error": str(e)}

        if not posts:
            logger.error("No posts generated — aborting")
            self.telegram.alert("Content Agent", "Generated 0 posts — check Claude prompt")
            return {"status": "empty"}

        profile_id = self.buffer.get_twitter_profile_id()
        if not profile_id:
            logger.error("No Twitter profile in Buffer")
            self.telegram.alert(
                "Content Agent — Buffer issue",
                "No Twitter profile found. Connect Twitter in Buffer first.",
            )
            return {"status": "no_profile"}

        results = self.buffer.schedule_batch(posts, profile_id)

        summary = (
            f"*Weekly content scheduled*\n\n"
            f"Posts queued: {results['queued']}/{results['total']}\n"
            f"Failed: {results['failed']}\n\n"
            + "\n\n".join(f"{i+1}. {p[:80]}..." for i, p in enumerate(posts[:3]))
            + ("\n\n...and more" if len(posts) > 3 else "")
        )
        self.telegram.send(summary)

        return {
            "status": "scheduled",
            "queued": results["queued"],
            "failed": results["failed"],
            "posts": posts,
        }
