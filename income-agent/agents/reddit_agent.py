"""
Agent 3: Reddit Draft Agent
────────────────────────────
Trigger : Cron every day at 08:00
Action  : Claude writes a Reddit post → sends draft to your Telegram
You do  : Read it (30 sec) → copy → paste into Reddit → post
Why manual: Reddit bans bot-posted accounts. Human posting is non-negotiable.
Cost    : ~$0.003/day
"""
import logging
import os
from datetime import date
from typing import Optional
from core.claude_client import ClaudeClient
from core.telegram_client import TelegramClient

logger = logging.getLogger(__name__)

TOPICS = [
    ("Why I kept blowing accounts until I changed THIS one habit", "r/Daytrading"),
    ("The pre-trade checklist that saved my trading account (free PDF)", "r/Forex"),
    ("3 mental mistakes costing retail traders thousands — personal story", "r/stocks"),
    ("Revenge trading almost destroyed me. Here's how I stopped", "r/Daytrading"),
    ("Position sizing is 90% of trading. Here's the framework I use", "r/investing"),
    ("I lost $8k in one week. Here's the psychology breakdown", "r/Forex"),
    ("Free trading psychology checklist — 10 questions to ask before every trade", "r/StockMarket"),
]

SYSTEM_PROMPT = """You write authentic Reddit posts about trading psychology.
Your audience is retail traders who have lost money and are struggling mentally.

Write a Reddit post for the given title and subreddit. The post must:
- Sound like a genuine personal story or insight — NOT a sales pitch
- Be 150–250 words
- Add real value (specific tip or insight, not vague advice)
- Mention your free PDF checklist ONCE at the end, naturally
  Example closing: "I actually put together a free checklist of the 10 questions
  I ask myself before every trade — happy to share if useful. Just let me know."
- Use Reddit formatting (no markdown headers, just paragraphs)
- Feel written by someone who has genuinely lost money and figured something out
- NEVER say "I made a product" or "buy this" or use any sales language

Output only the post body (no title, no subreddit label). Plain text."""


class RedditAgent:
    def __init__(
        self,
        claude: ClaudeClient = None,
        telegram: TelegramClient = None,
    ):
        self.claude = claude or ClaudeClient()
        self.telegram = telegram or TelegramClient()
        self._topic_index = 0

    def _get_todays_topic(self) -> tuple:
        """Rotate through topics based on day of year."""
        day_of_year = date.today().timetuple().tm_yday
        return TOPICS[day_of_year % len(TOPICS)]

    def generate_post(self, title: str = None, subreddit: str = None) -> Optional[str]:
        """Generate a Reddit post for today's topic."""
        if not title or not subreddit:
            title, subreddit = self._get_todays_topic()

        logger.info(f"Generating Reddit post: {title[:50]}")

        user_prompt = (
            f"Title: {title}\n"
            f"Subreddit: {subreddit}\n"
            f"Today's date context: {date.today().strftime('%A %B %d, %Y')}\n\n"
            "Write the post body."
        )

        try:
            post = self.claude.ask(SYSTEM_PROMPT, user_prompt, max_tokens=500)
            return post
        except Exception as e:
            logger.error(f"Reddit post generation failed: {e}")
            return None

    def run(self) -> dict:
        """
        Daily run: generate post → send to Telegram with copy instructions.
        """
        title, subreddit = self._get_todays_topic()
        post = self.generate_post(title, subreddit)

        if not post:
            self.telegram.alert(
                "Reddit Agent — Error",
                "Failed to generate today's post. Claude API issue?",
            )
            return {"status": "error"}

        char_count = len(post)
        message = (
            f"*Reddit post ready — {date.today().strftime('%a %b %d')}*\n\n"
            f"*Subreddit:* {subreddit}\n"
            f"*Title:* {title}\n\n"
            f"{'─' * 25}\n\n"
            f"{post}\n\n"
            f"{'─' * 25}\n\n"
            f"_{char_count} chars_\n\n"
            f"*Steps:*\n"
            f"1. Open reddit.com → {subreddit}\n"
            f"2. Click 'Create Post'\n"
            f"3. Paste title above\n"
            f"4. Paste body above\n"
            f"5. Post — takes 60 seconds"
        )

        self.telegram.send(message)
        logger.info(f"Reddit draft sent to Telegram — {subreddit}")

        return {
            "status": "draft_sent",
            "title": title,
            "subreddit": subreddit,
            "char_count": char_count,
        }

    def run_comment_reply(self, comment_text: str, subreddit: str) -> Optional[str]:
        """
        Generate a reply to a comment on your post.
        You still paste it manually — agent writes it in seconds.
        """
        system = (
            "You reply to Reddit comments on trading psychology posts. "
            "Be helpful, genuine, and conversational. Under 100 words. "
            "Don't pitch anything unless they ask about the checklist."
        )
        user = f"Comment in {subreddit}: {comment_text}\n\nWrite a reply."
        try:
            reply = self.claude.ask(system, user, max_tokens=200)
            self.telegram.send_draft(
                "Reddit comment reply",
                reply,
                "Copy and paste this as a comment reply.",
            )
            return reply
        except Exception as e:
            logger.error(f"Comment reply failed: {e}")
            return None
