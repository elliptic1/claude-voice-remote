"""Configuration for Claude Voice Remote bot."""
import os
from pathlib import Path

# Telegram Bot Token - get from @BotFather
# Set via environment variable or replace directly
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8151777398:AAF8QhLrmhz_NF9CjbVfKwdMOLidAj-Sed0")

# Your Telegram user ID (for authorization)
# Get by messaging @userinfobot on Telegram
AUTHORIZED_USER_IDS = [
    int(uid) for uid in os.environ.get("AUTHORIZED_USER_IDS", "8404923730").split(",") if uid
]

# Claude Code settings
CLAUDE_CODE_PATH = os.environ.get("CLAUDE_CODE_PATH", "claude")
CLAUDE_WORKING_DIR = os.environ.get("CLAUDE_WORKING_DIR", "/media/todd/androiddev/workspace")

# Whisper settings
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "base")  # tiny, base, small, medium, large

# Database path
DB_PATH = Path(__file__).parent / "sessions.db"

# Anthropic API key for classifier (optional - can use Claude Code itself)
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# Response settings
MAX_MESSAGE_LENGTH = 4000  # Telegram limit is 4096
TRUNCATE_SUFFIX = "\n\n... (truncated)"
