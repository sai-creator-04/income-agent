"""
Agent 2: Content Agent
──────────────────────
Trigger : Cron every Sunday 09:00
Action  : Gemini writes 7 trading psychology posts
          → posts directly to Twitter/X via API
          → sends summary to Telegram
Cost    : ~$0.02/week (Gemini free tier)
"""
import logging
import os
import re
import json
import time
import hmac
import hashlib
import base64
import urllib.parse
from datetime import date
from typing import List
from core.claude_client import ClaudeClient
from core.buffer_client import BufferClient
from core.telegram_client import TelegramClient

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a social media content writer for a trading psychology brand.

Write exactly 7 Twitter/X posts about trading psychology — one per line, separated by blank lines.
Each post must:
- Be under 220 characters (leave room for hashtags)
- Give one actionable trading psychology tip or insight
- End with: "Full checklist -> [LINK]"
- Feel like advice from a real trader who has been through losses
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
HASHTAGS = "#tradingpsychology #daytrading"


class TwitterClient:
    """
    Posts tweets using Twitter API v2 with OAuth 1.0a.
    No external libraries needed — uses stdlib only.
    """
    def __init__(self):
        self.api_key = os.environ.get("TWITTER_API_KEY", "")
        self.api_secret = os.environ.get("TWITTER_API_SECRET", "")
        self.access_token = os.environ.get("TWITTER_ACCESS_TOKEN", "")
        self.access_token_secret = os.environ.get("TWITTER_ACCESS_TOKEN_SECRET", "")

    def _is_configured(self) -> bool:
        return all([self.api_key, self.api_secret, self.access_token, self.access_token_secret])

    def _oauth_header(self, method: str, url: str, params: dict) -> str:
        """Build OAuth 1.0a Authorization header."""
        import random
        nonce = base64.b64encode(
            hashlib.md5(str(random.random()).encode()).digest()
        ).decode().strip("=")
        timestamp = str(int(time.time()))

        oauth_params = {
            "oauth_consumer_key": self.api_key,
            "oauth_nonce": nonce,
            "oauth_signature_method": "HMAC-SHA1",
            "oauth_timestamp": timestamp,
            "oauth_token": self.access_token,
            "oauth_version": "1.0",
        }

        # Build signature base string
        all_params = {**oauth_params, **params}
        sorted_params = "&".join(
            f"{urllib.parse.quote(str(k), safe='')}={urllib.parse.quote(str(v), safe='')}"
            for k, v in sorted(all_params.items())
        )
        base_string = "&".join([
            method.upper(),
            urllib.parse.quote(url, safe=""),
            urllib.parse.quote(sorted_params, safe="")
        ])

        # Sign it
        signing_key = f"{urllib.parse.quote(self.api_secret, safe='')}&{urllib.parse.quote(self.access_token_secret, safe='')}"
        signature = base64.b64encode(
            hmac.new(signing_key.encode(), base_string.encode(), hashlib.sha1).digest()
        ).decode()
        oauth_params["oauth_signature"] = signature

        # Build header
        header = "OAuth " + ", ".join(
            f'{urllib.parse.quote(str(k), safe="")}="{urllib.parse.quote(str(v), safe="")}"'
            for k, v in sorted(oauth_params.items())
        )
        return header

    def post_tweet(self, text: str) -> dict:
        """Post a tweet. Returns result dict."""
        try:
            import requests
            url = "https://api.twitter.com/2/tweets"
            body = {"text": text}
            auth_header = self._oauth_header("POST", url, {})
            resp = requests.post(
                url,
                json=body,
                headers={
                    "Authorization": auth_header,
                    "Content-Type": "application/json",
                },
                timeout=15
            )
            if resp.status_code in (200, 201):
                data = resp.json()
                tweet_id = data.get("data", {}).get("id", "unknown")
                logger.info(f"Tweet posted: {tweet_id}")
                return {"success": True, "id": tweet_id}
            else:
                logger.error(f"Tweet failed {resp.status_code}: {resp.text[:200]}")
                return {"success": False, "error": resp.text[:200]}
        except Exception as e:
            logger.error(f"Tweet exception: {e}")
            return {"success": False, "error": str(e)}


class ContentAgent:
    def __init__(self, claude=None, buffer=None, telegram=None, gumroad_link=None):
        self.claude = claude or ClaudeClient()
        self.buffer = buffer or BufferClient()
        self.telegram = telegram or TelegramClient()
        self.gumroad_link = gumroad_link or os.environ.get("GUMROAD_LINK", TWEET_LINK)
        self.twitter = TwitterClient()

    def generate_posts(self) -> List[str]:
        logger.info("Generating weekly content batch...")
        raw = self.claude.ask(
            SYSTEM_PROMPT,
            f"Generate 7 posts for the week of {date.today().strftime('%B %d, %Y')}.",
            max_tokens=1200,
        )
        posts = self._parse_posts(raw)
        final = []
        for p in posts:
            p = p.replace("[LINK]", self.gumroad_link)
            p = p.replace("-> ", "→ ")
            # Add hashtags if they fit
            candidate = p + f" {HASHTAGS}"
            if len(candidate) <= 280:
                p = candidate
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

    def _post_to_twitter(self, posts: List[str]) -> dict:
        """Post all 7 tweets with a 30-second gap between each."""
        if not self.twitter._is_configured():
            logger.warning("Twitter not configured — skipping auto-posting")
            return {"posted": 0, "failed": 0, "skipped": True}

        posted = 0
        failed = 0
        for i, post in enumerate(posts):
            result = self.twitter.post_tweet(post)
            if result["success"]:
                posted += 1
                logger.info(f"Posted tweet {i+1}/{len(posts)}")
            else:
                failed += 1
                logger.error(f"Failed tweet {i+1}: {result.get('error')}")
            # Wait 30 seconds between tweets to avoid rate limits
            if i < len(posts) - 1:
                time.sleep(30)

        return {"posted": posted, "failed": failed, "skipped": False}

    def run(self) -> dict:
        try:
            posts = self.generate_posts()
        except Exception as e:
            logger.error(f"Content generation failed: {e}")
            self.telegram.alert("Content Agent Error", f"Failed to generate posts: {e}")
            return {"status": "error", "error": str(e)}

        if not posts:
            logger.error("No posts generated")
            self.telegram.alert("Content Agent", "Generated 0 posts — check prompt")
            return {"status": "empty"}

        # Save posts to file as backup
        try:
            with open("posts_ready.json", "w") as f:
                json.dump({
                    "date": date.today().isoformat(),
                    "posts": posts
                }, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not save posts file: {e}")

        # Post to Twitter
        twitter_result = self._post_to_twitter(posts)

        # Send summary to Telegram
        if twitter_result.get("skipped"):
            status_line = "_Twitter keys not configured — posts saved but not auto-posted_"
        else:
            status_line = (
                f"Twitter: {twitter_result['posted']}/{len(posts)} posted "
                f"{'✅' if twitter_result['failed'] == 0 else '⚠️'}"
            )

        preview = "\n\n".join(
            f"*{i+1}.* {p[:100]}..." for i, p in enumerate(posts[:3])
        )

        self.telegram.send(
            f"*Weekly content done — {date.today().strftime('%b %d')}*\n\n"
            f"{status_line}\n\n"
            f"*Preview (first 3):*\n\n{preview}\n\n"
            f"_{'4 more posts posted automatically' if len(posts) > 3 else ''}_"
        )

        return {
            "status": "done",
            "posts_generated": len(posts),
            "twitter": twitter_result,
        }