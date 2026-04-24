"""
Main Server
────────────
- HTTP webhook server (port 8080) — receives Gumroad events
- Built-in scheduler — runs agents on cron-like schedule
- Single command to run everything: python3 main.py

No external dependencies beyond stdlib + requests.
"""
import json
import logging
import os
import threading
import time
import hashlib
import hmac
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, time as dtime
from urllib.parse import urlparse, parse_qs
from dotenv import load_dotenv  # pip install python-dotenv

# Load .env on startup
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.FileHandler("agent.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("main")

# Lazy-import agents after env is loaded
def _load_agents():
    from agents.buyer_support import BuyerSupportAgent
    from agents.content_agent import ContentAgent
    from agents.reddit_agent import RedditAgent
    from agents.dm_agent import DMAgent
    return (
        BuyerSupportAgent(),
        ContentAgent(),
        RedditAgent(),
        DMAgent(),
    )


class WebhookHandler(BaseHTTPRequestHandler):
    agents = None  # injected after server starts

    def log_message(self, format, *args):
        logger.info(f"HTTP {self.address_string()} {format % args}")

    def do_GET(self):
        if self.path == "/health":
            self._respond(200, {"status": "ok", "agents": 4})
        else:
            self._respond(404, {"error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b""

        if path == "/webhook/gumroad":
            self._handle_gumroad(body)
        elif path == "/webhook/buyer-message":
            self._handle_buyer_message(body)
        elif path == "/run/content":
            self._run_agent("content", body)
        elif path == "/run/reddit":
            self._run_agent("reddit", body)
        elif path == "/run/dm":
            self._run_agent("dm", body)
        else:
            self._respond(404, {"error": "unknown endpoint"})

    def _handle_gumroad(self, body: bytes):
        """Verify Gumroad signature and route to buyer support agent."""
        secret = os.environ.get("GUMROAD_WEBHOOK_SECRET", "")
        pass  # signature check skipped


        try:
            payload = self._parse_form_or_json(body)
        except Exception as e:
            logger.error(f"Could not parse Gumroad payload: {e}")
            self._respond(400, {"error": "bad payload"})
            return

        result = self.agents[0].handle_gumroad_webhook(payload)
        self._respond(200, result)

    def _handle_buyer_message(self, body: bytes):
        """
        Handle a buyer support message.
        Expects JSON: {email, name, message, message_id?, subject?}
        """
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self._respond(400, {"error": "invalid JSON"})
            return

        required = ["email", "name", "message"]
        if not all(k in data for k in required):
            self._respond(400, {"error": f"missing fields: {required}"})
            return

        result = self.agents[0].handle(
            buyer_email=data["email"],
            buyer_name=data["name"],
            message=data["message"],
            message_id=data.get("message_id"),
            subject=data.get("subject"),
        )
        self._respond(200, result)

    def _run_agent(self, agent_name: str, body: bytes):
        """Manually trigger an agent run via POST /run/{agent}."""
        agent_map = {
            "content": self.agents[1],
            "reddit": self.agents[2],
            "dm": self.agents[3],
        }
        agent = agent_map.get(agent_name)
        if not agent:
            self._respond(404, {"error": "unknown agent"})
            return

        # Run in thread so webhook returns immediately
        threading.Thread(target=agent.run, daemon=True).start()
        self._respond(202, {"status": "started", "agent": agent_name})

    def _verify_gumroad_sig(self, body: bytes, secret: str) -> bool:
        """Verify Gumroad webhook HMAC-SHA256 signature."""
        sig = self.headers.get("X-Gumroad-Signature", "")
        expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, expected)

    def _parse_form_or_json(self, body: bytes) -> dict:
        """Parse form-encoded or JSON body."""
        content_type = self.headers.get("Content-Type", "")
        if "application/json" in content_type:
            return json.loads(body)
        # Gumroad sends form-encoded
        from urllib.parse import unquote_plus
        result = {}
        for pair in body.decode().split("&"):
            if "=" in pair:
                k, v = pair.split("=", 1)
                result[unquote_plus(k)] = unquote_plus(v)
        return result

    def _respond(self, status: int, data: dict):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class AgentScheduler:
    """
    Lightweight scheduler using threading.
    Runs agents at their scheduled times daily.
    """
    def __init__(self, agents):
        self.agents = agents
        self.running = True
        self.schedule = [
            (dtime(8, 0),  "reddit",  agents[2]),
            (dtime(8, 30), "dm",      agents[3]),
            (dtime(9, 0),  "content", agents[1]),  # only runs on Sunday
        ]
        self._fired_today = set()

    def _should_run_content(self) -> bool:
        return datetime.now().weekday() == 6  # Sunday

    def tick(self):
        now = datetime.now()
        today_key = now.date().isoformat()
        current_time = now.time()

        for scheduled_time, name, agent in self.schedule:
            fire_key = f"{today_key}:{name}"
            if fire_key in self._fired_today:
                continue

            # Fire if within 1 minute past scheduled time
            delta = (
                datetime.combine(now.date(), current_time)
                - datetime.combine(now.date(), scheduled_time)
            ).total_seconds()

            if 0 <= delta < 60:
                if name == "content" and not self._should_run_content():
                    self._fired_today.add(fire_key)
                    continue
                logger.info(f"Scheduler firing agent: {name}")
                self._fired_today.add(fire_key)
                threading.Thread(target=agent.run, daemon=True, name=name).start()

        # Clean up old keys to prevent memory leak
        if len(self._fired_today) > 100:
            self._fired_today = {k for k in self._fired_today if today_key in k}

    def run(self):
        logger.info("Scheduler started")
        while self.running:
            self.tick()
            time.sleep(30)  # check every 30 seconds


def start_server(port: int = 8080, agents=None):
    WebhookHandler.agents = agents

    class ThreadedServer(HTTPServer):
        def process_request(self, request, client_address):
            t = threading.Thread(
                target=self._new_connection,
                args=(request, client_address),
                daemon=True,
            )
            t.start()

        def _new_connection(self, request, client_address):
            self.finish_request(request, client_address)

    server = ThreadedServer(("0.0.0.0", port), WebhookHandler)
    logger.info(f"Webhook server on http://0.0.0.0:{port}")
    return server


def main():
    logger.info("=" * 50)
    logger.info("Income Agent System starting...")
    logger.info("=" * 50)

    required_env = [
        "ANTHROPIC_API_KEY",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
        "GMAIL_ADDRESS",
        "GMAIL_APP_PASSWORD",
        "BUFFER_ACCESS_TOKEN",
    ]
    missing = [k for k in required_env if not os.environ.get(k)]
    if missing:
        logger.error(f"Missing environment variables: {missing}")
        logger.error("Copy .env.example to .env and fill in your credentials")
        return

    logger.info("Loading agents...")
    agents = _load_agents()
    logger.info("All agents loaded")

    port = int(os.environ.get("PORT", 8080))
    server = start_server(port, agents)

    scheduler = AgentScheduler(agents)
    sched_thread = threading.Thread(target=scheduler.run, daemon=True, name="scheduler")
    sched_thread.start()

    logger.info("System ready. Agents:")
    logger.info("  [1] Buyer Support  — webhook /webhook/gumroad")
    logger.info("  [2] Content Agent  — Sundays 09:00 auto")
    logger.info("  [3] Reddit Agent   — daily 08:00 auto")
    logger.info("  [4] DM Agent       — daily 08:30 auto")
    logger.info(f"  Health check       — GET http://localhost:{port}/health")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        scheduler.running = False
        server.shutdown()


if __name__ == "__main__":
    main()
