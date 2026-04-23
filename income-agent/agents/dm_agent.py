"""
Agent 4: Cold DM Agent
───────────────────────
Trigger : Cron every day at 08:30
Action  : Search Twitter for traders in pain → Claude writes personalised DMs
          → sends list to your Telegram → YOU paste and send (10 min)
Why manual sending: Twitter/Instagram ban mass-DM bots.
Cost    : ~$0.01/day (Apify free tier + Claude Haiku)
"""
import logging
import os
import requests
from typing import List, Optional
from datetime import date
from core.claude_client import ClaudeClient
from core.telegram_client import TelegramClient

logger = logging.getLogger(__name__)

SEARCH_QUERIES = [
    "blew my trading account",
    "lost money trading today",
    "revenge trading again",
    "trading losses",
    "can't stop overtrading",
]

SYSTEM_PROMPT = """You write short, genuine, empathetic cold DMs for a trading psychology resource.

Given a trader's tweet about losses or struggles, write a DM that:
- Opens by referencing something SPECIFIC from their tweet (not generic)
- Offers genuine empathy — you've been there
- Mentions you have a free trading psychology checklist that helped you
- Ends with a soft ask (not a hard sell)
- Sounds like a helpful stranger, not a marketer
- Is under 80 words
- No emojis, no exclamation marks

Example tone:
"Saw your tweet about revenge trading — that cycle is brutal and I've been exactly there.
Made a simple pre-trade checklist after my worst losing month that helped me pause before
re-entering badly. Happy to share if useful — it's free."

Output ONLY the DM text. Nothing else."""


class DMAgent:
    def __init__(
        self,
        claude: ClaudeClient = None,
        telegram: TelegramClient = None,
        apify_token: str = None,
        gumroad_link: str = None,
    ):
        self.claude = claude or ClaudeClient()
        self.telegram = telegram or TelegramClient()
        self.apify_token = apify_token or os.environ.get("APIFY_API_TOKEN", "")
        self.gumroad_link = gumroad_link or os.environ.get("GUMROAD_LINK", "")

    def search_twitter(self, query: str, max_results: int = 5) -> List[dict]:
        """
        Search Twitter via Apify's Twitter Scraper actor.
        Returns list of {username, text, url} dicts.
        Apify free tier: $5 credit/month — enough for daily searches.
        """
        if not self.apify_token:
            logger.warning("No APIFY_API_TOKEN — returning mock data for testing")
            return self._mock_results(query)

        actor_url = "https://api.apify.com/v2/acts/apidojo~tweet-scraper/run-sync-get-dataset-items"
        payload = {
            "searchTerms": [query],
            "maxItems": max_results,
            "queryType": "Latest",
            "lang": "en",
        }
        try:
            resp = requests.post(
                actor_url,
                params={"token": self.apify_token},
                json=payload,
                timeout=60,
            )
            resp.raise_for_status()
            items = resp.json()
            results = []
            for item in items:
                author = item.get("author", {})
                results.append({
                    "username": author.get("userName", "unknown"),
                    "text": item.get("text", ""),
                    "url": item.get("url", ""),
                })
            logger.info(f"Apify returned {len(results)} tweets for '{query}'")
            return results
        except requests.exceptions.RequestException as e:
            logger.error(f"Apify search failed: {e}")
            return []

    def _mock_results(self, query: str) -> List[dict]:
        """Fallback mock data for testing without Apify."""
        return [
            {
                "username": "trader_example",
                "text": f"Just lost 3% account on {query} again. Frustrating.",
                "url": "https://twitter.com/trader_example/status/123",
            }
        ]

    def write_dm(self, tweet_text: str, username: str) -> Optional[str]:
        """Generate a personalised DM for a specific tweet."""
        user_prompt = (
            f"Twitter username: @{username}\n"
            f"Their tweet: {tweet_text}\n\n"
            "Write the DM."
        )
        try:
            dm = self.claude.ask(SYSTEM_PROMPT, user_prompt, max_tokens=200)
            if self.gumroad_link and "[LINK]" in dm:
                dm = dm.replace("[LINK]", self.gumroad_link)
            return dm
        except Exception as e:
            logger.error(f"DM generation failed for @{username}: {e}")
            return None

    def run(self, max_dms: int = 10) -> dict:
        """
        Daily run: search Twitter → write DMs → send to Telegram.
        You get a Telegram message with all DMs ready to copy-paste.
        """
        logger.info("DM Agent starting daily run...")
        targets = []

        for query in SEARCH_QUERIES:
            results = self.search_twitter(query, max_results=3)
            targets.extend(results)
            if len(targets) >= max_dms:
                break

        targets = targets[:max_dms]

        if not targets:
            self.telegram.alert(
                "DM Agent — No targets found",
                "Apify returned no results. Check token or try again tomorrow.",
            )
            return {"status": "no_targets"}

        dm_list = []
        for t in targets:
            dm = self.write_dm(t["text"], t["username"])
            if dm:
                dm_list.append({
                    "username": t["username"],
                    "tweet": t["text"][:120],
                    "dm": dm,
                    "profile_url": f"https://twitter.com/{t['username']}",
                })

        self._send_to_telegram(dm_list)

        return {
            "status": "dms_ready",
            "count": len(dm_list),
            "targets": [d["username"] for d in dm_list],
        }

    def _send_to_telegram(self, dm_list: List[dict]) -> None:
        """Format and send the DM list to Telegram."""
        if not dm_list:
            return

        header = (
            f"*{len(dm_list)} DMs ready — {date.today().strftime('%b %d')}*\n"
            f"Open each profile → paste DM → send\n"
            f"{'─' * 30}"
        )
        self.telegram.send(header)

        for i, item in enumerate(dm_list, 1):
            msg = (
                f"*DM {i}/{len(dm_list)}*\n"
                f"Profile: {item['profile_url']}\n"
                f"Their tweet: _{item['tweet'][:100]}_\n\n"
                f"*Your DM:*\n{item['dm']}"
            )
            self.telegram.send(msg)

        self.telegram.send(
            f"_Total: {len(dm_list)} DMs. Estimated send time: ~10 minutes._"
        )
