#!/usr/bin/env python3
"""
Claude Voice Remote - Telegram bot for remote Claude Code access.

Send voice messages or text to control Claude Code on your home Linux box.
Features smart AI-powered routing to automatically direct messages to the right project.
"""
import asyncio
import logging
import sys
from pathlib import Path

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import base64
import io

from config import (
    AUTHORIZED_USER_IDS,
    MAX_MESSAGE_LENGTH,
    TELEGRAM_BOT_TOKEN,
    TRUNCATE_SUFFIX,
)
from claude_runner import run_claude, test_claude_connection
from orchestrator import get_session_manager, get_router, Session
from transcribe import download_and_transcribe

# Set up logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def is_authorized(user_id: int) -> bool:
    """Check if user is authorized to use the bot."""
    if not AUTHORIZED_USER_IDS:
        # No restrictions if no authorized users configured
        logger.warning("No AUTHORIZED_USER_IDS configured - allowing all users")
        return True
    return user_id in AUTHORIZED_USER_IDS


def truncate_message(text: str, max_length: int = MAX_MESSAGE_LENGTH) -> str:
    """Truncate message to fit Telegram limits."""
    if len(text) <= max_length:
        return text
    return text[: max_length - len(TRUNCATE_SUFFIX)] + TRUNCATE_SUFFIX


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    user_id = update.effective_user.id

    if not is_authorized(user_id):
        await update.message.reply_text(
            f"Unauthorized. Your user ID is: {user_id}\n"
            "Add this to AUTHORIZED_USER_IDS in config."
        )
        return

    await update.message.reply_text(
        "Claude Voice Remote\n\n"
        "Send me text or voice messages and I'll forward them to Claude Code.\n\n"
        "Commands:\n"
        "/status - Check connection & current session\n"
        "/new <name> - Start a new project session\n"
        "/list - List active sessions\n"
        "/switch <name> - Switch to a session\n"
        "/delete <name> - Delete a session\n"
        "/help - Show this message"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    await start_command(update, context)


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /status command - check Claude Code connection and current session."""
    user_id = update.effective_user.id

    if not is_authorized(user_id):
        await update.message.reply_text("Unauthorized")
        return

    await update.message.reply_text("Checking status...")

    # Check Claude Code connection
    claude_ok = await test_claude_connection()

    # Get current session info
    sm = get_session_manager()
    current_session_id = context.user_data.get("current_db_session_id")
    current_session = None
    if current_session_id:
        current_session = sm.get_session_by_id(current_session_id)

    status_lines = []
    if claude_ok:
        status_lines.append("Claude Code: Connected")
    else:
        status_lines.append("Claude Code: NOT CONNECTED")
        status_lines.append("  - Check CLAUDE_CODE_PATH in config")
        status_lines.append("  - Ensure you're authenticated")

    if current_session:
        status_lines.append(f"\nCurrent session: {current_session.name}")
        status_lines.append(f"  Messages: {current_session.message_count}")
        status_lines.append(f"  Last used: {current_session.last_used.strftime('%Y-%m-%d %H:%M')}")
    else:
        status_lines.append("\nNo active session (will auto-route)")

    sessions = sm.get_all_sessions()
    status_lines.append(f"\nTotal sessions: {len(sessions)}")

    await update.message.reply_text("\n".join(status_lines))


async def process_message(
    message_text: str,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Process a message (text or transcribed voice) and send to Claude Code."""
    sm = get_session_manager()
    router = get_router()

    # Send typing indicator
    await update.message.chat.send_action("typing")

    # Smart routing: determine which session this message belongs to
    current_db_id = context.user_data.get("current_db_session_id")
    session = None

    if current_db_id:
        # Use current session if set
        session = sm.get_session_by_id(current_db_id)

    if not session:
        # Auto-route based on message content
        session = await router.classify_message(message_text)

    if session:
        logger.info(f"Routing to session: {session.name}")
        # Update context
        context.user_data["current_db_session_id"] = session.id
    else:
        # Create a default session if none exist
        logger.info("No session found, creating default")
        session = sm.create_session("Default", description="Auto-created session")
        context.user_data["current_db_session_id"] = session.id

    # Run Claude Code with the session's Claude session ID
    response = await run_claude(
        prompt=message_text,
        session_id=session.session_id if session.session_id else None,
        continue_recent=not session.session_id,  # Continue recent if no specific session
        working_dir=session.working_dir if session.working_dir else None,
    )

    if response.success:
        # Update session with Claude's session ID if we got one
        if response.session_id and response.session_id != session.session_id:
            sm.update_session_id(session.id, response.session_id)

        # Update usage stats
        sm.update_last_used(session.id)
        sm.add_message_to_history(session.id, message_text)

        # Extract and update keywords for better future routing
        keywords = router.extract_keywords(message_text, response.output)
        if keywords:
            existing = session.keywords.split(",") if session.keywords else []
            new_keywords = list(set(existing + keywords))[:10]
            sm.update_keywords(session.id, ",".join(new_keywords))

        # Send response
        reply_text = truncate_message(response.output)

        # Add session indicator
        session_indicator = f"[{session.name}]\n\n"
        reply_text = session_indicator + reply_text

        await update.message.reply_text(reply_text)

        # Send any screenshots as photos
        if response.images:
            for i, img_data in enumerate(response.images[:5]):  # Limit to 5 images
                try:
                    # Decode base64 image
                    img_bytes = base64.b64decode(img_data)
                    img_file = io.BytesIO(img_bytes)
                    img_file.name = f"screenshot_{i+1}.jpg"
                    await update.message.reply_photo(
                        photo=img_file,
                        caption=f"Screenshot {i+1}" if len(response.images) > 1 else "Screenshot"
                    )
                except Exception as e:
                    logger.error(f"Failed to send screenshot: {e}")
    else:
        await update.message.reply_text(f"Error: {response.error}")


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming text messages - forward to Claude Code."""
    user_id = update.effective_user.id

    if not is_authorized(user_id):
        logger.warning(f"Unauthorized message from user {user_id}")
        return

    message_text = update.message.text
    logger.info(f"Received text from {user_id}: {message_text[:100]}...")

    await process_message(message_text, update, context)


async def handle_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming voice messages - transcribe and forward to Claude Code."""
    user_id = update.effective_user.id

    if not is_authorized(user_id):
        logger.warning(f"Unauthorized voice message from user {user_id}")
        return

    logger.info(f"Received voice from {user_id}: {update.message.voice.duration}s")

    # Acknowledge receipt
    await update.message.reply_text("Transcribing voice message...")

    # Download and transcribe
    try:
        text = await download_and_transcribe(
            context.bot,
            update.message.voice
        )

        if not text:
            await update.message.reply_text(
                "Could not transcribe voice message. Please try again or send text."
            )
            return

        # Show transcription
        await update.message.reply_text(f"Heard: \"{text}\"")

        # Process the transcribed text
        await process_message(text, update, context)

    except Exception as e:
        logger.exception("Voice message error")
        await update.message.reply_text(f"Voice processing error: {str(e)}")


async def new_session_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /new command - start a new session."""
    user_id = update.effective_user.id

    if not is_authorized(user_id):
        return

    args = context.args
    if not args:
        await update.message.reply_text(
            "Usage: /new <project_name> [description]\n"
            "Example: /new MiniNews Working on the news app"
        )
        return

    project_name = args[0]
    description = " ".join(args[1:]) if len(args) > 1 else ""

    sm = get_session_manager()

    # Check if session already exists
    existing = sm.get_session_by_name(project_name)
    if existing:
        await update.message.reply_text(
            f"Session '{project_name}' already exists. Use /switch {project_name}"
        )
        return

    # Create new session
    session = sm.create_session(project_name, description=description)
    context.user_data["current_db_session_id"] = session.id

    # Clear Claude session ID so we start fresh
    context.user_data.pop("current_session_id", None)

    await update.message.reply_text(
        f"Created new session: {project_name}\n"
        f"Description: {description or '(none)'}\n\n"
        "Your next message will start a fresh Claude Code conversation."
    )


async def list_sessions_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /list command - list sessions."""
    user_id = update.effective_user.id

    if not is_authorized(user_id):
        return

    sm = get_session_manager()
    sessions = sm.get_all_sessions()

    if not sessions:
        await update.message.reply_text(
            "No sessions yet. Send a message to create one automatically,\n"
            "or use /new <name> to create one explicitly."
        )
        return

    current_id = context.user_data.get("current_db_session_id")

    lines = ["Sessions:\n"]
    for s in sessions:
        indicator = " *" if s.id == current_id else ""
        lines.append(
            f"  {s.name}{indicator}\n"
            f"    Messages: {s.message_count} | "
            f"Last: {s.last_used.strftime('%m/%d %H:%M')}"
        )
        if s.description:
            lines.append(f"    {s.description}")

    lines.append(f"\n(* = current)")
    lines.append("\nUse /switch <name> to change sessions")

    await update.message.reply_text("\n".join(lines))


async def switch_session_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /switch command - switch session."""
    user_id = update.effective_user.id

    if not is_authorized(user_id):
        return

    args = context.args
    if not args:
        await update.message.reply_text("Usage: /switch <session_name>")
        return

    name = " ".join(args)
    sm = get_session_manager()
    session = sm.get_session_by_name(name)

    if not session:
        # Try partial match
        sessions = sm.get_all_sessions()
        matches = [s for s in sessions if name.lower() in s.name.lower()]
        if len(matches) == 1:
            session = matches[0]
        elif len(matches) > 1:
            names = ", ".join(s.name for s in matches)
            await update.message.reply_text(f"Multiple matches: {names}\nBe more specific.")
            return
        else:
            await update.message.reply_text(
                f"Session '{name}' not found.\n"
                "Use /list to see available sessions."
            )
            return

    context.user_data["current_db_session_id"] = session.id

    await update.message.reply_text(
        f"Switched to: {session.name}\n"
        f"Messages: {session.message_count}"
    )


async def delete_session_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /delete command - delete a session."""
    user_id = update.effective_user.id

    if not is_authorized(user_id):
        return

    args = context.args
    if not args:
        await update.message.reply_text("Usage: /delete <session_name>")
        return

    name = " ".join(args)
    sm = get_session_manager()
    session = sm.get_session_by_name(name)

    if not session:
        await update.message.reply_text(f"Session '{name}' not found.")
        return

    # Clear if it's the current session
    if context.user_data.get("current_db_session_id") == session.id:
        context.user_data.pop("current_db_session_id", None)

    sm.delete_session(session.id)

    await update.message.reply_text(f"Deleted session: {session.name}")


def main() -> None:
    """Run the bot."""
    if TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("ERROR: Set your Telegram bot token in config.py or TELEGRAM_BOT_TOKEN env var")
        print("\nTo get a token:")
        print("1. Message @BotFather on Telegram")
        print("2. Send /newbot and follow instructions")
        print("3. Copy the token to config.py")
        sys.exit(1)

    # Create application
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("new", new_session_command))
    application.add_handler(CommandHandler("list", list_sessions_command))
    application.add_handler(CommandHandler("switch", switch_session_command))
    application.add_handler(CommandHandler("delete", delete_session_command))

    # Message handlers
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice_message))

    # Start the bot
    logger.info("Starting Claude Voice Remote bot...")
    logger.info("Send a message to your bot on Telegram to begin!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
