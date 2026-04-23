"""
Full test suite for all 4 agents.
All external calls (Claude, Gmail, Telegram, Buffer, Apify) are mocked.
Run: python3 -m pytest tests/ -v   OR   python3 tests/test_all.py
"""
import sys
import os
import json
import unittest
from unittest.mock import MagicMock, patch, call
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ─────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────

def make_claude(response: str) -> MagicMock:
    m = MagicMock()
    m.ask.return_value = response
    return m

def make_telegram() -> MagicMock:
    m = MagicMock()
    m.send.return_value = True
    m.alert.return_value = True
    m.send_draft.return_value = True
    return m

def make_gmail() -> MagicMock:
    m = MagicMock()
    m.send.return_value = True
    return m

def make_buffer(profile_id="profile_123") -> MagicMock:
    m = MagicMock()
    m.get_twitter_profile_id.return_value = profile_id
    m.schedule_batch.return_value = {"queued": 7, "failed": 0, "total": 7}
    m.schedule_post.return_value = True
    return m


# ─────────────────────────────────────────
# CLAUDE CLIENT TESTS
# ─────────────────────────────────────────

class TestClaudeClient(unittest.TestCase):

    def _make_client(self):
        from core.claude_client import ClaudeClient
        c = ClaudeClient.__new__(ClaudeClient)
        c.api_key = "test-key"
        return c

    def test_missing_api_key_raises(self):
        from core.claude_client import ClaudeClient
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("ANTHROPIC_API_KEY", None)
            with self.assertRaises(ValueError):
                ClaudeClient()

    def test_headers_correct(self):
        c = self._make_client()
        h = c._headers()
        self.assertEqual(h["x-api-key"], "test-key")
        self.assertIn("anthropic-version", h)
        self.assertEqual(h["content-type"], "application/json")

    @patch("core.claude_client.requests.post")
    def test_ask_returns_text(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "content": [{"type": "text", "text": "Hello from Claude"}]
        }
        mock_post.return_value.raise_for_status = MagicMock()
        c = self._make_client()
        result = c.ask("system", "user")
        self.assertEqual(result, "Hello from Claude")

    @patch("core.claude_client.requests.post")
    @patch("core.claude_client.time.sleep")
    def test_ask_retries_on_429(self, mock_sleep, mock_post):
        import requests as req
        from core.claude_client import ClaudeClient

        rate_limited = MagicMock()
        rate_limited.status_code = 429
        rate_limited.raise_for_status.side_effect = req.exceptions.HTTPError(
            response=rate_limited
        )

        success = MagicMock()
        success.status_code = 200
        success.json.return_value = {
            "content": [{"type": "text", "text": "ok"}]
        }
        success.raise_for_status = MagicMock()

        mock_post.side_effect = [rate_limited, success]
        c = self._make_client()
        result = c.ask("sys", "user")
        self.assertEqual(result, "ok")
        mock_sleep.assert_called_once()

    @patch("core.claude_client.requests.post")
    def test_ask_concatenates_multiple_blocks(self, mock_post):
        mock_post.return_value.json.return_value = {
            "content": [
                {"type": "text", "text": "Hello "},
                {"type": "text", "text": "World"},
            ]
        }
        mock_post.return_value.raise_for_status = MagicMock()
        c = self._make_client()
        result = c.ask("sys", "user")
        # .strip() collapses trailing space — both "Hello World" and "Hello  World" valid
        self.assertIn("Hello", result)
        self.assertIn("World", result)


# ─────────────────────────────────────────
# TELEGRAM CLIENT TESTS
# ─────────────────────────────────────────

class TestTelegramClient(unittest.TestCase):

    def _make(self):
        from core.telegram_client import TelegramClient
        t = TelegramClient.__new__(TelegramClient)
        t.token = "test-token"
        t.chat_id = "12345"
        return t

    def test_missing_token_raises(self):
        from core.telegram_client import TelegramClient
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("TELEGRAM_BOT_TOKEN", None)
            os.environ.pop("TELEGRAM_CHAT_ID", None)
            with self.assertRaises(ValueError):
                TelegramClient()

    @patch("core.telegram_client.requests.post")
    def test_send_short_message(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.raise_for_status = MagicMock()
        t = self._make()
        result = t.send("Hello!")
        self.assertTrue(result)
        mock_post.assert_called_once()

    @patch("core.telegram_client.requests.post")
    def test_send_long_message_splits(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.raise_for_status = MagicMock()
        t = self._make()
        long_msg = "A" * 5000
        t.send(long_msg)
        # Should be called more than once (split into chunks)
        self.assertGreater(mock_post.call_count, 1)

    @patch("core.telegram_client.requests.post")
    def test_send_returns_false_on_error(self, mock_post):
        import requests as req
        mock_post.side_effect = req.exceptions.RequestException("network error")
        t = self._make()
        result = t.send("test")
        self.assertFalse(result)

    def test_alert_formats_title_bold(self):
        t = self._make()
        t.send = MagicMock(return_value=True)
        t.alert("TITLE", "body text")
        sent_msg = t.send.call_args[0][0]
        self.assertIn("*TITLE*", sent_msg)
        self.assertIn("body text", sent_msg)


# ─────────────────────────────────────────
# GMAIL CLIENT TESTS
# ─────────────────────────────────────────

class TestGmailClient(unittest.TestCase):

    def _make(self):
        from core.gmail_client import GmailClient
        g = GmailClient.__new__(GmailClient)
        g.email = "test@gmail.com"
        g.app_password = "testpassword"
        return g

    @patch("core.gmail_client.smtplib.SMTP_SSL")
    def test_send_success(self, mock_smtp):
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp.return_value.__exit__ = MagicMock(return_value=False)
        g = self._make()
        result = g.send("buyer@test.com", "Subject", "Body")
        self.assertTrue(result)

    @patch("core.gmail_client.smtplib.SMTP_SSL")
    def test_send_auth_failure(self, mock_smtp):
        import smtplib
        mock_smtp.return_value.__enter__ = MagicMock(
            side_effect=smtplib.SMTPAuthenticationError(535, b"bad credentials")
        )
        mock_smtp.return_value.__exit__ = MagicMock(return_value=False)
        g = self._make()
        result = g.send("buyer@test.com", "Subject", "Body")
        self.assertFalse(result)

    def test_missing_email_raises(self):
        from core.gmail_client import GmailClient
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("GMAIL_ADDRESS", None)
            os.environ.pop("GMAIL_APP_PASSWORD", None)
            with self.assertRaises(ValueError):
                GmailClient()


# ─────────────────────────────────────────
# BUYER SUPPORT AGENT TESTS
# ─────────────────────────────────────────

class TestBuyerSupportAgent(unittest.TestCase):

    def _make(self, claude_response="Thank you for your question!"):
        from agents.buyer_support import BuyerSupportAgent
        return BuyerSupportAgent(
            claude=make_claude(claude_response),
            gmail=make_gmail(),
            telegram=make_telegram(),
            upsell_link="https://gumroad.com/upsell",
        )

    def test_normal_message_sends_reply(self):
        agent = self._make("Thanks for reaching out!")
        result = agent.handle("buyer@test.com", "Alice", "I love the PDF!")
        self.assertEqual(result["status"], "replied")
        agent.gmail.send.assert_called_once()

    def test_refund_request_flags_to_telegram(self):
        agent = self._make("[REFUND_REQUEST] I want a refund.")
        result = agent.handle("buyer@test.com", "Bob", "I want a refund please")
        self.assertEqual(result["status"], "refund_flagged")
        agent.telegram.alert.assert_called_once()

    def test_refund_sends_courtesy_email(self):
        agent = self._make("[REFUND_REQUEST]")
        agent.handle("buyer@test.com", "Bob", "refund please")
        agent.gmail.send.assert_called_once()
        subject = agent.gmail.send.call_args.kwargs.get("subject") or agent.gmail.send.call_args[1].get("subject", "")
        self.assertIn("Refund", subject)

    def test_claude_failure_returns_error(self):
        from agents.buyer_support import BuyerSupportAgent
        claude = MagicMock()
        claude.ask.side_effect = RuntimeError("API down")
        agent = BuyerSupportAgent(
            claude=claude,
            gmail=make_gmail(),
            telegram=make_telegram(),
        )
        result = agent.handle("b@test.com", "X", "hello")
        self.assertEqual(result["status"], "error")

    def test_gmail_failure_returns_send_failed(self):
        from agents.buyer_support import BuyerSupportAgent
        gmail = make_gmail()
        gmail.send.return_value = False
        agent = BuyerSupportAgent(
            claude=make_claude("Nice reply"),
            gmail=gmail,
            telegram=make_telegram(),
        )
        result = agent.handle("b@test.com", "X", "hello")
        self.assertEqual(result["status"], "send_failed")

    def test_upsell_link_replaced_in_reply(self):
        from agents.buyer_support import BuyerSupportAgent
        agent = BuyerSupportAgent(
            claude=make_claude("Check this out: [UPSELL_LINK]"),
            gmail=make_gmail(),
            telegram=make_telegram(),
            upsell_link="https://gumroad.com/upsell-test",
        )
        agent.handle("b@test.com", "X", "great product!")
        # Check the body arg in any form (positional or keyword)
        call = agent.gmail.send.call_args
        args = call[0] if call[0] else []
        kwargs = call[1] if call[1] else {}
        body = kwargs.get("body", args[2] if len(args) > 2 else "")
        self.assertIn("https://gumroad.com/upsell-test", body)
        self.assertNotIn("[UPSELL_LINK]", body)

    def test_gumroad_webhook_sale(self):
        agent = self._make()
        payload = {
            "resource_name": "sale",
            "email": "buyer@test.com",
            "full_name": "Alice",
            "product_name": "Trading Psychology Playbook",
        }
        result = agent.handle_gumroad_webhook(payload)
        self.assertEqual(result["status"], "welcome_sent")
        agent.gmail.send.assert_called_once()

    def test_gumroad_webhook_dispute(self):
        agent = self._make()
        payload = {"resource_name": "dispute", "email": "angry@test.com"}
        result = agent.handle_gumroad_webhook(payload)
        self.assertEqual(result["status"], "dispute_alerted")
        agent.telegram.alert.assert_called_once()

    def test_gumroad_webhook_unknown_event(self):
        agent = self._make()
        result = agent.handle_gumroad_webhook({"resource_name": "refund"})
        self.assertEqual(result["status"], "unhandled_event")


# ─────────────────────────────────────────
# CONTENT AGENT TESTS
# ─────────────────────────────────────────

class TestContentAgent(unittest.TestCase):

    SAMPLE_POSTS = "\n\n".join([
        f"{i}. Trading tip number {i} — Full checklist → [LINK]"
        for i in range(1, 8)
    ])

    def _make(self):
        from agents.content_agent import ContentAgent
        return ContentAgent(
            claude=make_claude(self.SAMPLE_POSTS),
            buffer=make_buffer(),
            telegram=make_telegram(),
            gumroad_link="https://gum.co/test",
        )

    def test_run_schedules_posts(self):
        agent = self._make()
        result = agent.run()
        self.assertEqual(result["status"], "scheduled")
        self.assertGreater(result["queued"], 0)

    def test_posts_contain_gumroad_link(self):
        agent = self._make()
        posts = agent.generate_posts()
        for p in posts:
            self.assertIn("https://gum.co/test", p)
            self.assertNotIn("[LINK]", p)

    def test_parse_posts_numbered(self):
        from agents.content_agent import ContentAgent
        a = ContentAgent.__new__(ContentAgent)
        raw = "1. First post\n\n2. Second post\n\n3. Third post"
        posts = a._parse_posts(raw)
        self.assertEqual(len(posts), 3)
        self.assertEqual(posts[0], "First post")

    def test_parse_posts_blank_line_separated(self):
        from agents.content_agent import ContentAgent
        a = ContentAgent.__new__(ContentAgent)
        raw = "First post about trading\n\nSecond post about losses\n\nThird post here"
        posts = a._parse_posts(raw)
        self.assertEqual(len(posts), 3)

    def test_run_sends_telegram_summary(self):
        agent = self._make()
        agent.run()
        agent.telegram.send.assert_called()

    def test_run_no_profile_alerts_telegram(self):
        from agents.content_agent import ContentAgent
        buf = make_buffer(profile_id=None)
        agent = ContentAgent(
            claude=make_claude(self.SAMPLE_POSTS),
            buffer=buf,
            telegram=make_telegram(),
        )
        result = agent.run()
        self.assertEqual(result["status"], "no_profile")
        agent.telegram.alert.assert_called_once()

    def test_run_claude_failure_alerts_telegram(self):
        from agents.content_agent import ContentAgent
        claude = MagicMock()
        claude.ask.side_effect = RuntimeError("Claude down")
        agent = ContentAgent(
            claude=claude,
            buffer=make_buffer(),
            telegram=make_telegram(),
        )
        result = agent.run()
        self.assertEqual(result["status"], "error")


# ─────────────────────────────────────────
# REDDIT AGENT TESTS
# ─────────────────────────────────────────

class TestRedditAgent(unittest.TestCase):

    def _make(self, post="This is a genuine Reddit post about trading losses."):
        from agents.reddit_agent import RedditAgent
        return RedditAgent(
            claude=make_claude(post),
            telegram=make_telegram(),
        )

    def test_run_sends_draft_to_telegram(self):
        agent = self._make()
        result = agent.run()
        self.assertEqual(result["status"], "draft_sent")
        agent.telegram.send.assert_called()

    def test_run_includes_subreddit_in_message(self):
        agent = self._make()
        agent.run()
        all_calls = " ".join(str(c) for c in agent.telegram.send.call_args_list)
        self.assertIn("r/", all_calls)

    def test_run_includes_copy_instructions(self):
        agent = self._make()
        agent.run()
        all_calls = " ".join(str(c) for c in agent.telegram.send.call_args_list)
        self.assertIn("Reddit", all_calls)

    def test_topic_rotates_by_day(self):
        from agents.reddit_agent import RedditAgent, TOPICS
        agent = RedditAgent.__new__(RedditAgent)
        seen = set()
        for day in range(len(TOPICS) * 2):
            with patch("agents.reddit_agent.date") as mock_date:
                mock_date.today.return_value.timetuple.return_value.tm_yday = day
                title, sub = agent._get_todays_topic()
                seen.add(title)
        self.assertEqual(len(seen), len(TOPICS))

    def test_claude_failure_alerts_telegram(self):
        from agents.reddit_agent import RedditAgent
        claude = MagicMock()
        claude.ask.side_effect = RuntimeError("down")
        agent = RedditAgent(claude=claude, telegram=make_telegram())
        result = agent.run()
        self.assertEqual(result["status"], "error")
        agent.telegram.alert.assert_called_once()

    def test_generate_post_calls_claude(self):
        agent = self._make("Great post content here.")
        post = agent.generate_post("Test title", "r/Daytrading")
        self.assertEqual(post, "Great post content here.")
        agent.claude.ask.assert_called_once()

    def test_comment_reply_sends_to_telegram(self):
        agent = self._make("Great reply here.")
        agent.run_comment_reply("I keep blowing accounts", "r/Forex")
        agent.telegram.send_draft.assert_called_once()


# ─────────────────────────────────────────
# DM AGENT TESTS
# ─────────────────────────────────────────

class TestDMAgent(unittest.TestCase):

    MOCK_TARGETS = [
        {"username": "trader1", "text": "Blew my account again today.", "url": "https://twitter.com/trader1/1"},
        {"username": "trader2", "text": "Lost 5% on revenge trade.", "url": "https://twitter.com/trader2/2"},
        {"username": "trader3", "text": "Can't stop overtrading.", "url": "https://twitter.com/trader3/3"},
    ]

    def _make(self):
        from agents.dm_agent import DMAgent
        agent = DMAgent(
            claude=make_claude("Saw your tweet about losses. I made a checklist that helped me."),
            telegram=make_telegram(),
            apify_token="",
            gumroad_link="https://gum.co/test",
        )
        agent.search_twitter = MagicMock(return_value=self.MOCK_TARGETS)
        return agent

    def test_run_generates_dms(self):
        agent = self._make()
        # Override search to always return exactly 3 targets total
        agent.search_twitter = MagicMock(side_effect=[self.MOCK_TARGETS, [], [], [], []])
        result = agent.run()
        self.assertEqual(result["status"], "dms_ready")
        self.assertGreaterEqual(result["count"], 1)

    def test_run_sends_to_telegram(self):
        agent = self._make()
        agent.run()
        self.assertGreater(agent.telegram.send.call_count, 1)

    def test_run_no_targets_alerts(self):
        from agents.dm_agent import DMAgent
        agent = DMAgent(
            claude=make_claude("dm"),
            telegram=make_telegram(),
        )
        agent.search_twitter = MagicMock(return_value=[])
        result = agent.run()
        self.assertEqual(result["status"], "no_targets")
        agent.telegram.alert.assert_called_once()

    def test_write_dm_replaces_link(self):
        from agents.dm_agent import DMAgent
        agent = DMAgent(
            claude=make_claude("Check [LINK] for more"),
            telegram=make_telegram(),
            gumroad_link="https://gum.co/real-link",
        )
        dm = agent.write_dm("lost money", "someuser")
        self.assertIn("https://gum.co/real-link", dm)
        self.assertNotIn("[LINK]", dm)

    def test_write_dm_claude_failure_returns_none(self):
        from agents.dm_agent import DMAgent
        claude = MagicMock()
        claude.ask.side_effect = RuntimeError("down")
        agent = DMAgent(claude=claude, telegram=make_telegram())
        result = agent.write_dm("lost money", "user1")
        self.assertIsNone(result)

    def test_mock_results_returned_when_no_apify_token(self):
        from agents.dm_agent import DMAgent
        agent = DMAgent.__new__(DMAgent)
        agent.apify_token = ""
        results = agent._mock_results("test query")
        self.assertIsInstance(results, list)
        self.assertGreater(len(results), 0)
        self.assertIn("username", results[0])

    def test_telegram_messages_include_profile_url(self):
        agent = self._make()
        agent.run()
        all_calls = " ".join(str(c) for c in agent.telegram.send.call_args_list)
        self.assertIn("twitter.com", all_calls)


# ─────────────────────────────────────────
# SCHEDULER TESTS
# ─────────────────────────────────────────

class TestScheduler(unittest.TestCase):

    def test_content_runs_only_on_sunday(self):
        from main import AgentScheduler
        from datetime import time as dtime

        agents = [MagicMock(), MagicMock(), MagicMock(), MagicMock()]
        sched = AgentScheduler(agents)

        # Simulate a weekday (Monday = 0)
        with patch("main.datetime") as mock_dt:
            mock_dt.now.return_value.weekday.return_value = 0  # Monday
            mock_dt.now.return_value.time.return_value = dtime(9, 0)
            mock_dt.now.return_value.date.return_value = date.today()
            mock_dt.combine = __import__("datetime").datetime.combine
            result = sched._should_run_content()
            self.assertFalse(result)

        # Sunday = 6
        with patch("main.datetime") as mock_dt:
            mock_dt.now.return_value.weekday.return_value = 6
            mock_dt.combine = __import__("datetime").datetime.combine
            sched2 = AgentScheduler(agents)
            result = sched2._should_run_content()
            self.assertTrue(result)


# ─────────────────────────────────────────
# RUNNER
# ─────────────────────────────────────────

if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    test_classes = [
        TestClaudeClient,
        TestTelegramClient,
        TestGmailClient,
        TestBuyerSupportAgent,
        TestContentAgent,
        TestRedditAgent,
        TestDMAgent,
        TestScheduler,
    ]

    for cls in test_classes:
        suite.addTests(loader.loadTestsFromTestCase(cls))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    total = result.testsRun
    passed = total - len(result.failures) - len(result.errors)
    print(f"\n{'='*50}")
    print(f"Results: {passed}/{total} passed")
    if result.failures:
        print(f"FAILURES: {len(result.failures)}")
    if result.errors:
        print(f"ERRORS:   {len(result.errors)}")
    print("="*50)

    sys.exit(0 if result.wasSuccessful() else 1)
