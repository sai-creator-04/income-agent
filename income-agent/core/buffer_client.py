"""
Buffer API client for scheduling social media posts.
Free tier: 10 posts queued at a time. Enough for 1 post/day.
Get your access token: buffer.com/developers/apps
"""
import requests
import os
import logging
from typing import Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)

BUFFER_API = "https://api.bufferapp.com/1"


class BufferClient:
    def __init__(self, access_token: str = None):
        self.token = access_token or os.environ.get("BUFFER_ACCESS_TOKEN")
        if not self.token:
            raise ValueError("BUFFER_ACCESS_TOKEN not set")

    def _params(self, extra: dict = None) -> dict:
        base = {"access_token": self.token}
        if extra:
            base.update(extra)
        return base

    def get_profiles(self) -> List[dict]:
        """Return all connected social media profiles."""
        try:
            resp = requests.get(
                f"{BUFFER_API}/profiles.json",
                params=self._params(),
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Buffer get_profiles failed: {e}")
            return []

    def get_twitter_profile_id(self) -> Optional[str]:
        """Find the Twitter/X profile ID automatically."""
        for profile in self.get_profiles():
            if profile.get("service") in ("twitter", "twitter_v2"):
                pid = profile.get("id")
                logger.info(f"Twitter profile ID: {pid}")
                return pid
        logger.warning("No Twitter profile found in Buffer account")
        return None

    def schedule_post(self, text: str, profile_id: str) -> bool:
        """Add a post to the Buffer queue for the given profile."""
        try:
            resp = requests.post(
                f"{BUFFER_API}/updates/create.json",
                params=self._params(),
                data={
                    "text": text,
                    "profile_ids[]": profile_id,
                    "shorten": True,
                },
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            success = data.get("success", False)
            if success:
                logger.info(f"Post queued in Buffer: {text[:60]}...")
            else:
                logger.error(f"Buffer rejected post: {data}")
            return success
        except requests.exceptions.RequestException as e:
            logger.error(f"Buffer schedule_post failed: {e}")
            return False

    def schedule_batch(self, posts: List[str], profile_id: str) -> dict:
        """
        Schedule a list of posts. Returns summary dict.
        Buffer free tier queues them in order — posts go live
        at your pre-set schedule times.
        """
        results = {"queued": 0, "failed": 0, "total": len(posts)}
        for post in posts:
            if self.schedule_post(post, profile_id):
                results["queued"] += 1
            else:
                results["failed"] += 1
        logger.info(
            f"Buffer batch: {results['queued']}/{results['total']} queued"
        )
        return results
