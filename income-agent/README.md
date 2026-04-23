# Income Agent System
### 4 AI agents. 12 min/day. Runs 24/7 on free hosting.

Automates buyer support, Twitter content, Reddit drafts, and cold DM research
for your Gumroad digital product business. Built on Claude AI + free-tier tools.

---

## What each agent does

| Agent | Trigger | What it does | Your effort |
|---|---|---|---|
| Buyer Support | Gumroad sale/message | Claude reads → writes reply → Gmail sends | 0 min |
| Content | Every Sunday 09:00 | Writes 7 posts → schedules in Buffer | 0 min |
| Reddit Draft | Mon–Sat 08:00 | Writes post → sends to Telegram | 2 min (copy-paste) |
| DM Finder | Mon–Sat 08:30 | Finds targets → writes DMs → sends to Telegram | 10 min (paste & send) |

---

## Setup — complete step by step

### Prerequisites
- Python 3.9+ installed
- Git installed
- A Gumroad account with your product live
- A Gmail account

---

### Step 1 — Get the code

```bash
git clone https://github.com/YOUR_USERNAME/income-agent.git
cd income-agent
bash setup.sh
```

This installs dependencies, creates your `.env` file, and runs the test suite.

---

### Step 2 — Get your Anthropic API key

1. Go to **console.anthropic.com**
2. Sign up / log in
3. Click **API Keys** → **Create Key**
4. Copy the key (starts with `sk-ant-`)
5. Paste into `.env`:
   ```
   ANTHROPIC_API_KEY=sk-ant-your-key-here
   ```

> Cost: ~$1–3/month running all 4 agents daily. Haiku model is used throughout.

---

### Step 3 — Create your Telegram bot

This is your notification inbox. Every draft, alert, and DM lands here.

1. Open Telegram → search **@BotFather** → start chat
2. Send: `/newbot`
3. Choose a name: e.g. `Income Agent`
4. Choose a username: e.g. `myincomeagent_bot`
5. BotFather sends you a token like: `1234567890:ABCdefGhIjKlMn...`
6. Paste into `.env`:
   ```
   TELEGRAM_BOT_TOKEN=1234567890:ABCdefGhIjKlMn...
   ```
7. Now get your chat ID:
   - Search **@userinfobot** on Telegram → start chat → it replies with your ID
   - Paste into `.env`:
   ```
   TELEGRAM_CHAT_ID=987654321
   ```
8. Start your bot: search for your bot username → click Start

---

### Step 4 — Set up Gmail App Password

This lets the agent send emails from your Gmail without your real password.

1. Go to **myaccount.google.com/security**
2. Make sure **2-Step Verification** is ON (required)
3. Search for **"App passwords"** in the search bar → click it
4. Select app: **Mail** → Select device: **Other** → type `Income Agent`
5. Click **Generate** → copy the 16-character password (e.g. `abcd efgh ijkl mnop`)
6. Paste into `.env`:
   ```
   GMAIL_ADDRESS=you@gmail.com
   GMAIL_APP_PASSWORD=abcd efgh ijkl mnop
   ```

> The spaces in the password are fine — include them as-is.

---

### Step 5 — Set up Buffer for Twitter scheduling

1. Go to **buffer.com** → sign up free
2. Click **Connect a Channel** → choose **Twitter/X** → authorize
3. Go to **buffer.com/developers/apps** → click **Create an App**
4. Fill in: name `Income Agent`, website `http://localhost`, description anything
5. After creating, scroll to **Access Token** → copy it
6. Paste into `.env`:
   ```
   BUFFER_ACCESS_TOKEN=your-access-token-here
   ```
7. In Buffer dashboard: set your posting schedule (recommend 9am daily)

---

### Step 6 — Set up your Gumroad product

1. Upload your Trading Psychology PDF to **gumroad.com**
2. Set price to $25
3. In product settings, find the **short URL** (e.g. `https://gum.co/tradingpsych`)
4. Paste into `.env`:
   ```
   GUMROAD_LINK=https://gum.co/tradingpsych
   GUMROAD_UPSELL_LINK=https://gum.co/your-second-product
   ```
5. Generate a webhook secret (any random string):
   ```bash
   python3 -c "import secrets; print(secrets.token_hex(20))"
   ```
6. Paste into `.env`:
   ```
   GUMROAD_WEBHOOK_SECRET=the-random-string-you-generated
   ```

---

### Step 7 — Set up Apify (DM target finder)

1. Go to **apify.com** → sign up free (get $5 credit/month)
2. Click your avatar → **Settings** → **Integrations**
3. Copy your **Personal API Token**
4. Paste into `.env`:
   ```
   APIFY_API_TOKEN=apify_api_your-token
   ```

> If you skip this, the DM agent uses mock data for testing — real searches need the token.

---

### Step 8 — Deploy to Railway (free 24/7 hosting)

Railway gives you a free server that runs your agents around the clock.

1. Go to **railway.app** → sign up with GitHub
2. Click **New Project** → **Deploy from GitHub repo**
3. Select your `income-agent` repo
4. Railway detects Python automatically
5. Go to your project → **Variables** tab → add ALL your `.env` variables one by one:
   - `ANTHROPIC_API_KEY`
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
   - `GMAIL_ADDRESS`
   - `GMAIL_APP_PASSWORD`
   - `BUFFER_ACCESS_TOKEN`
   - `GUMROAD_LINK`
   - `GUMROAD_UPSELL_LINK`
   - `GUMROAD_WEBHOOK_SECRET`
   - `APIFY_API_TOKEN`
   - `PORT` = `8080`
6. Railway deploys automatically → wait ~2 minutes
7. Go to **Settings** → **Networking** → **Generate Domain**
8. Copy your URL: `https://income-agent-production.up.railway.app`
9. Test it:
   ```bash
   curl https://YOUR-URL.railway.app/health
   # Should return: {"status": "ok", "agents": 4}
   ```

---

### Step 9 — Connect Gumroad webhook

1. In Gumroad: **Settings** → **Advanced** → **Webhooks**
2. Paste your Railway URL + `/webhook/gumroad`:
   ```
   https://YOUR-URL.railway.app/webhook/gumroad
   ```
3. Enter your `GUMROAD_WEBHOOK_SECRET`
4. Check: **Sale**, **Dispute**
5. Click **Save**
6. Test: click **Send test ping** — you should get a Telegram message

---

### Step 10 — Import Make.com scenarios

Make.com is the cron scheduler — it triggers your agents on schedule.

1. Go to **make.com** → sign up free
2. Go to **Scenarios** → click **⋮** → **Import Blueprint**
3. Import each file from `make_scenarios/` one by one:
   - `01_gumroad_buyer_support.json` — backup webhook handler
   - `02_weekly_content.json` — Sunday content scheduler
   - `03_daily_reddit.json` — daily Reddit draft
   - `04_daily_dm.json` — daily DM finder

4. In **each scenario**, replace `YOUR-RAILWAY-URL` with your actual Railway URL
5. In Make.com → **Organization** → **Variables**, add:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
6. Turn each scenario **ON**

---

### Step 11 — Test everything

```bash
# Test buyer support (simulates a buyer message)
curl -X POST https://YOUR-URL.railway.app/webhook/buyer-message \
  -H "Content-Type: application/json" \
  -d '{"email":"test@test.com","name":"Test Buyer","message":"How do I open the PDF?"}'
# Check your Gmail — auto-reply should arrive in <60 seconds

# Test Reddit agent (get a draft on Telegram now)
curl -X POST https://YOUR-URL.railway.app/run/reddit
# Check Telegram — draft should arrive in ~30 seconds

# Test DM agent
curl -X POST https://YOUR-URL.railway.app/run/dm
# Check Telegram — DM list should arrive in ~60 seconds

# Test content agent (generates + queues posts in Buffer)
curl -X POST https://YOUR-URL.railway.app/run/content
# Check Buffer — 7 posts should be queued
```

---

## Daily routine after setup

| Time | What arrives | Your action | Time |
|---|---|---|---|
| 08:00 | Reddit draft in Telegram | Copy → paste → post on Reddit | 2 min |
| 08:30 | 10 DMs in Telegram | Open Twitter → paste → send each | 10 min |
| Any time | Buyer emails | Nothing — auto-handled | 0 min |
| Sunday | Buffer posts queued | Nothing — auto-scheduled | 0 min |

**Total: 12 minutes per day.**

---

## Costs

| Service | Free tier | Your usage | Cost |
|---|---|---|---|
| Anthropic API | Pay per use | ~$1–3/month | ~$2 |
| Railway | $5 credit/month | ~$3/month | $0 |
| Make.com | 1,000 ops/month | ~200 ops/month | $0 |
| Buffer | 10 posts queued | 7 posts/week | $0 |
| Apify | $5 credit/month | ~$1/month | $0 |
| Telegram | Free | Free | $0 |
| Gumroad | 10% per sale | Only on revenue | variable |

**Total monthly cost: ~$2**

---

## Troubleshooting

**Buyer auto-reply not sending**
- Check Gmail App Password is 16 chars (no spaces) — actually spaces are fine, include them
- Check 2-Step Verification is ON in Google Account
- Check `agent.log` on Railway: Logs tab

**Telegram messages not arriving**
- Send `/start` to your bot first (required once)
- Verify TELEGRAM_CHAT_ID is your personal ID not the bot's ID
- Use @userinfobot to re-check your chat ID

**Buffer not scheduling posts**
- Reconnect Twitter in Buffer (tokens expire occasionally)
- Check Buffer free tier hasn't hit 10-post limit — clear old posts

**Railway deploy failing**
- Check all environment variables are set in Railway Variables tab
- Check `runtime.txt` says `python-3.12`
- Check Procfile says `web: python3 main.py`

**Make.com scenario not firing**
- Check timezone in scenario matches your local time
- Check scenario is toggled ON (green)
- Check Railway URL has no trailing slash

---

## File structure

```
income-agent/
├── core/
│   ├── claude_client.py      # Claude API wrapper with retry logic
│   ├── telegram_client.py    # Telegram bot notifications
│   ├── gmail_client.py       # Gmail SMTP auto-replies
│   └── buffer_client.py      # Buffer Twitter scheduling
├── agents/
│   ├── buyer_support.py      # Agent 1: auto-replies to buyers
│   ├── content_agent.py      # Agent 2: weekly Twitter posts
│   ├── reddit_agent.py       # Agent 3: daily Reddit drafts
│   └── dm_agent.py           # Agent 4: DM target finder
├── make_scenarios/
│   ├── 01_gumroad_buyer_support.json
│   ├── 02_weekly_content.json
│   ├── 03_daily_reddit.json
│   └── 04_daily_dm.json
├── tests/
│   └── test_all.py           # 44 tests, all passing
├── deploy/
│   └── railway.toml
├── main.py                   # Server + scheduler (single entry point)
├── requirements.txt
├── Procfile
├── runtime.txt
├── setup.sh                  # One-command setup
└── .env.example              # Credentials template
```

---

## Scaling beyond $330

Once agents are running and you're getting consistent sales:

1. **Add more products** — same Gumroad setup, update `GUMROAD_LINK` to point to a bundle
2. **Add more subreddits** — edit `TOPICS` list in `agents/reddit_agent.py`
3. **Add Instagram DMs** — same DM agent, different search (Apify has Instagram scrapers)
4. **Add email list** — connect Gumroad to ConvertKit free (1,000 subscribers free)
5. **Add a second product** — Reddit agent starts mentioning it after 30 days of trust-building

---

*Built with Claude Sonnet. Tests: 44/44 passing. Estimated setup time: 2–3 hours.*
