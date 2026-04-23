"""
Agent 1: Buyer Support Agent
─────────────────────────────
Trigger : Gumroad webhook (POST /webhook/gumroad)
Action  : Claude reads buyer email/question → writes reply → Gmail sends it
Fallback: Refund requests → Telegram alert to you
Cost    : ~$0.001 per reply (Haiku model)
"""
import logging
import os
from typing import Optional
from core.claude_client import ClaudeClient
from core.gmail_client import GmailClient
from core.telegram_client import TelegramClient

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a warm, professional customer support assistant for a digital product business.
You sell a "Trading Psychology Playbook" PDF — a 20-page guide covering mental mistakes traders make and a daily pre-trade checklist.

Your job: read the buyer's message and write a short, helpful reply (under 150 words).

RULES:
- Sound human and genuine, not like a bot
- If they have a download issue: tell them to check spam folder, or click the Gumroad link in their purchase email again
- If they ask about content: give a brief helpful answer (don't reveal full PDF content)
- If they ask for a refund: DO NOT process it — reply with the special tag [REFUND_REQUEST]
- If they're happy/complimentary: thank them warmly and mention the upsell (see below)
- Never mention competitors
- Sign off as: "The Trading Psychology Team"

UPSELL (mention only when buyer is happy):
"If you found this useful, our 'Risk Management Masterclass' PDF covers position sizing and stop-loss strategies in depth — available at 60% off for existing customers: [UPSELL_LINK]"

Reply in plain text. No markdown. Just the email body."""

REFUND_ALERT_TEMPLATE = """*REFUND REQUEST — action needed*

Buyer: {email}
Message: {message}

Reply to them and process if within 30 days of purchase.
Gumroad refunds: gumroad.com/sales"""


class BuyerSupportAgent:
    def __init__(
        self,
        claude: ClaudeClient = None,
        gmail: GmailClient = None,
        telegram: TelegramClient = None,
        upsell_link: str = None,
    ):
        self.claude = claude or ClaudeClient()
        self.gmail = gmail or GmailClient()
        self.telegram = telegram or TelegramClient()
        self.upsell_link = upsell_link or os.environ.get(
            "GUMROAD_UPSELL_LINK", "https://gumroad.com/your-upsell-link"
        )

    def handle(self, buyer_email: str, buyer_name: str, message: str,
               message_id: Optional[str] = None, subject: str = None) -> dict:
        """
        Main handler. Called when a buyer message arrives.
        Returns result dict with status and details.
        """
        logger.info(f"Handling buyer message from {buyer_email}")

        user_prompt = (
            f"Buyer name: {buyer_name}\n"
            f"Buyer email: {buyer_email}\n"
            f"Their message:\n{message}"
        )

        try:
            reply = self.claude.ask(SYSTEM_PROMPT, user_prompt)
        except Exception as e:
            logger.error(f"Claude failed for buyer support: {e}")
            return {"status": "error", "error": str(e)}

        if "[REFUND_REQUEST]" in reply:
            return self._handle_refund(buyer_email, buyer_name, message)

        reply = reply.replace("[UPSELL_LINK]", self.upsell_link)

        reply_subject = subject or "Re: Your Trading Psychology Playbook"
        if not reply_subject.startswith("Re:"):
            reply_subject = f"Re: {reply_subject}"

        sent = self.gmail.send(
            to=buyer_email,
            subject=reply_subject,
            body=reply,
            reply_to_message_id=message_id,
        )

        if sent:
            logger.info(f"Auto-reply sent to {buyer_email}")
            return {"status": "replied", "buyer": buyer_email, "reply_preview": reply[:100]}
        else:
            logger.error(f"Failed to send reply to {buyer_email}")
            return {"status": "send_failed", "buyer": buyer_email}

    def _handle_refund(self, email: str, name: str, message: str) -> dict:
        """Alert you via Telegram for manual refund handling."""
        alert = REFUND_ALERT_TEMPLATE.format(email=email, message=message[:300])
        self.telegram.alert("REFUND REQUEST", alert)
        logger.warning(f"Refund request from {email} — Telegram alert sent")

        courtesy_reply = (
            f"Hi {name},\n\n"
            "Thank you for reaching out. We've received your refund request and our "
            "team will review it within 24 hours. We'll follow up shortly.\n\n"
            "The Trading Psychology Team"
        )
        self.gmail.send(
            to=email,
            subject="Re: Your Trading Psychology Playbook — Refund Request Received",
            body=courtesy_reply,
        )
        return {"status": "refund_flagged", "buyer": email}

    def handle_gumroad_webhook(self, payload: dict) -> dict:
        """
        Parse a Gumroad sale/dispute webhook payload and route it.
        Gumroad sends POST to your /webhook/gumroad endpoint.
        """
        event = payload.get("resource_name", "unknown")
        logger.info(f"Gumroad webhook event: {event}")

        if event == "sale":
            buyer_email = payload.get("email", "")
            buyer_name = payload.get("full_name", "Customer")
            product = payload.get("product_name", "your purchase")

            welcome = (
                f"Hi {buyer_name},\n\n"
                f"Thank you for purchasing the Trading Psychology Playbook! "
                f"Your download link is in this email from Gumroad.\n\n"
                f"Quick tip: open the PDF on your computer for the best experience "
                f"— the checklist is on page 18.\n\n"
                f"Any questions, just reply here.\n\n"
                f"The Trading Psychology Team"
            )
            self.gmail.send(
                to=buyer_email,
                subject=f"Your Trading Psychology Playbook is ready",
                body=welcome,
            )
            return {"status": "welcome_sent", "buyer": buyer_email}

        elif event == "dispute":
            email = payload.get("email", "unknown")
            self.telegram.alert(
                "GUMROAD DISPUTE",
                f"Buyer {email} opened a dispute. Check Gumroad dashboard immediately."
            )
            return {"status": "dispute_alerted"}

        return {"status": "unhandled_event", "event": event}
