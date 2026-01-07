"""Configuration for Claude Voice Remote bot."""
import os
from pathlib import Path

# Telegram Bot Token - get from @BotFather
# Set via environment variable or replace directly
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

# Your Telegram user ID (for authorization)
# Get by messaging @userinfobot on Telegram
# Leave empty string as default to allow all users (not recommended for production)
AUTHORIZED_USER_IDS = [
    int(uid) for uid in os.environ.get("AUTHORIZED_USER_IDS", "").split(",") if uid
]

# Claude Code settings
CLAUDE_CODE_PATH = os.environ.get("CLAUDE_CODE_PATH", "claude")
CLAUDE_WORKING_DIR = os.environ.get("CLAUDE_WORKING_DIR", os.path.expanduser("~/workspace"))

# Whisper settings
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "base")  # tiny, base, small, medium, large

# Database path
DB_PATH = Path(__file__).parent / "sessions.db"

# Anthropic API key for classifier (optional - can use Claude Code itself)
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# Response settings
MAX_MESSAGE_LENGTH = 4000  # Telegram limit is 4096
TRUNCATE_SUFFIX = "\n\n... (truncated)"
