#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# Income Agent — setup.sh
# Run once: bash setup.sh
# ─────────────────────────────────────────────────────────────
set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
ok()   { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[!!]${NC} $1"; }
info() { echo -e "${CYAN}[--]${NC} $1"; }
fail() { echo -e "${RED}[FAIL]${NC} $1"; exit 1; }

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "   Income Agent — Setup"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 1. Python check
info "Checking Python..."
python --version &>/dev/null || fail "Python not found. Install from python.org"
PY_VER=$(python -c "import sys; print(sys.version_info.minor)")
[ "$PY_VER" -ge 9 ] || fail "Python 3.9+ required (you have 3.$PY_VER)"
ok "Python $(python --version)"

# 2. Install dependencies
info "Installing dependencies..."
pip install -r requirements.txt -q || fail "pip install failed"
ok "Dependencies installed"

# 3. Setup .env
if [ ! -f .env ]; then
    cp .env.example .env
    warn ".env created from template — edit it with your credentials before running!"
    echo ""
    echo "  Open .env and fill in:"
    echo "  • ANTHROPIC_API_KEY"
    echo "  • TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID"
    echo "  • GMAIL_ADDRESS + GMAIL_APP_PASSWORD"
    echo "  • BUFFER_ACCESS_TOKEN"
    echo "  • GUMROAD_LINK + GUMROAD_UPSELL_LINK"
    echo "  • APIFY_API_TOKEN (optional — for DM agent)"
    echo ""
else
    ok ".env already exists"
fi

# 4. Validate .env has been filled in
if grep -q "your-key-here" .env 2>/dev/null; then
    warn ".env still has placeholder values — fill it in before launching!"
fi

# 5. Run tests
info "Running test suite..."
python tests/test_all.py 2>&1 | tail -6
ok "Test suite complete"

# 6. Validate credentials if .env is filled
info "Validating credentials..."
python - <<'PYEOF'
import os
from dotenv import load_dotenv
load_dotenv()

checks = {
    "ANTHROPIC_API_KEY": lambda v: v.startswith("sk-ant-"),
    "TELEGRAM_BOT_TOKEN": lambda v: ":" in v,
    "TELEGRAM_CHAT_ID": lambda v: v.isdigit(),
    "GMAIL_ADDRESS": lambda v: "@gmail.com" in v,
    "GMAIL_APP_PASSWORD": lambda v: len(v.replace(" ","")) >= 16,
    "BUFFER_ACCESS_TOKEN": lambda v: len(v) > 10,
    "GUMROAD_LINK": lambda v: "gum.co" in v or "gumroad.com" in v,
}

RED="\033[0;31m"; GREEN="\033[0;32m"; YELLOW="\033[1;33m"; NC="\033[0m"
all_good = True
for key, validator in checks.items():
    val = os.environ.get(key, "")
    if not val or "your-" in val or "placeholder" in val:
        print(f"{YELLOW}[SKIP]{NC} {key} — not set yet")
        all_good = False
    elif validator(val):
        print(f"{GREEN}[OK]{NC}   {key}")
    else:
        print(f"{RED}[BAD]{NC}  {key} — value looks wrong, double-check it")
        all_good = False

if all_good:
    print(f"\n{GREEN}All credentials look good — ready to launch!{NC}")
else:
    print(f"\n{YELLOW}Fill in the skipped/bad values in .env then run: python main.py{NC}")
PYEOF

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Setup complete."
echo ""
echo "  To launch: python main.py"
echo "  Health:    curl http://localhost:8080/health"
echo "  Logs:      tail -f agent.log"
echo ""
echo "  Manual triggers:"
echo "  curl -X POST http://localhost:8080/run/reddit"
echo "  curl -X POST http://localhost:8080/run/content"
echo "  curl -X POST http://localhost:8080/run/dm"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
