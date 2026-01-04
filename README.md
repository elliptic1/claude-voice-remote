# Claude Voice Remote

Send voice messages or text from Telegram to control Claude Code on your home Linux box.

## Features

- **Voice messages**: Speak into Telegram, Whisper transcribes, Claude Code executes
- **Smart routing**: AI automatically determines which project your message relates to
- **Session management**: Track multiple projects with separate conversation contexts
- **No port forwarding**: Works via Telegram's infrastructure

## Quick Start

### 1. Create a Telegram Bot

1. Open Telegram and message [@BotFather](https://t.me/botfather)
2. Send `/newbot` and follow the prompts
3. Copy the bot token (looks like `123456789:ABC...`)

### 2. Get Your Telegram User ID

1. Message [@userinfobot](https://t.me/userinfobot) on Telegram
2. It will reply with your user ID (a number)

### 3. Install Dependencies

```bash
cd claude-voice-remote
pip install -r requirements.txt
```

For voice support, you also need ffmpeg:
```bash
# Ubuntu/Debian
sudo apt install ffmpeg

# macOS
brew install ffmpeg
```

### 4. Configure

Edit `config.py` or set environment variables:

```bash
export TELEGRAM_BOT_TOKEN="your_bot_token"
export AUTHORIZED_USER_IDS="your_user_id"
export CLAUDE_WORKING_DIR="/path/to/your/workspace"
```

### 5. Run

```bash
python bot.py
```

### 6. (Optional) Run as Service

```bash
# Edit the service file with your paths/credentials
sudo cp systemd/claude-voice-remote.service /etc/systemd/system/

# Edit the service file
sudo nano /etc/systemd/system/claude-voice-remote.service

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable claude-voice-remote
sudo systemctl start claude-voice-remote

# Check logs
journalctl -u claude-voice-remote -f
```

## Usage

### Basic Commands

- `/start` or `/help` - Show help
- `/status` - Check Claude Code connection and current session
- `/new <name> [description]` - Create new project session
- `/list` - List all sessions
- `/switch <name>` - Switch to a session
- `/delete <name>` - Delete a session

### Smart Routing

The bot automatically routes messages to the right project based on content:

- Mentions of project names (e.g., "in MiniNews...")
- Keywords learned from previous messages
- AI classification (if Anthropic API key configured)

You usually don't need to manually switch sessions!

### Voice Messages

1. Hold the microphone button in Telegram
2. Speak your command
3. Bot transcribes and shows you what it heard
4. Sends to Claude Code

## Architecture

```
Phone (Telegram)
    ↓ voice/text
Linux Box:
    Telegram Bot (bot.py)
        ↓
    Whisper (transcribe.py) - voice → text
        ↓
    Orchestrator (orchestrator.py) - route to session
        ↓
    Claude Runner (claude_runner.py) - execute
        ↓
    Claude Code (headless mode)
```

## Configuration Options

| Variable | Default | Description |
|----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | (required) | Bot token from @BotFather |
| `AUTHORIZED_USER_IDS` | (empty = all) | Comma-separated user IDs |
| `CLAUDE_CODE_PATH` | `claude` | Path to Claude Code CLI |
| `CLAUDE_WORKING_DIR` | `~/workspace` | Default working directory |
| `WHISPER_MODEL` | `base` | Whisper model (tiny/base/small/medium/large) |
| `ANTHROPIC_API_KEY` | (optional) | For AI-powered routing |

## Troubleshooting

### "Claude Code connection failed"
- Ensure Claude Code is installed: `claude --version`
- Check authentication: `claude auth status`
- Verify `CLAUDE_CODE_PATH` points to the right binary

### Voice messages not working
- Install ffmpeg: `sudo apt install ffmpeg`
- Check Whisper model loaded: `python transcribe.py test.ogg`
- Try a smaller model if memory issues: `WHISPER_MODEL=tiny`

### Bot not responding
- Check bot token is correct
- Ensure your user ID is in `AUTHORIZED_USER_IDS`
- Check logs: `journalctl -u claude-voice-remote -f`

## License

MIT
