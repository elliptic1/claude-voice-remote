"""Voice transcription using Whisper."""
import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Optional

from config import WHISPER_MODEL

logger = logging.getLogger(__name__)

# Lazy-load whisper model to save memory
_model = None


def get_whisper_model():
    """Get or load the Whisper model."""
    global _model
    if _model is None:
        try:
            from faster_whisper import WhisperModel

            logger.info(f"Loading Whisper model: {WHISPER_MODEL}")
            # Use CPU by default, change to "cuda" if you have GPU
            _model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
            logger.info("Whisper model loaded")
        except ImportError:
            logger.error(
                "faster-whisper not installed. Run: pip install faster-whisper"
            )
            raise
    return _model


async def transcribe_audio(audio_path: Path) -> Optional[str]:
    """
    Transcribe audio file to text using Whisper.

    Args:
        audio_path: Path to audio file (OGG from Telegram or any format)

    Returns:
        Transcribed text or None on error
    """
    try:
        model = get_whisper_model()

        # Run transcription in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        segments, info = await loop.run_in_executor(
            None,
            lambda: model.transcribe(str(audio_path), beam_size=5)
        )

        # Collect all segments
        text_parts = []
        for segment in segments:
            text_parts.append(segment.text)

        full_text = " ".join(text_parts).strip()

        logger.info(f"Transcribed {info.duration:.1f}s audio: {full_text[:100]}...")
        return full_text

    except Exception as e:
        logger.exception(f"Transcription error: {e}")
        return None


async def transcribe_telegram_voice(voice_file_path: Path) -> Optional[str]:
    """
    Transcribe a Telegram voice message.

    Telegram sends voice as OGG Opus format, which Whisper handles natively.

    Args:
        voice_file_path: Path to downloaded voice file

    Returns:
        Transcribed text or None on error
    """
    return await transcribe_audio(voice_file_path)


async def download_and_transcribe(bot, voice) -> Optional[str]:
    """
    Download voice file from Telegram and transcribe it.

    Args:
        bot: Telegram bot instance
        voice: Voice message object from Telegram

    Returns:
        Transcribed text or None on error
    """
    try:
        # Download voice file to temp location
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp_file:
            tmp_path = Path(tmp_file.name)

        voice_file = await bot.get_file(voice.file_id)
        await voice_file.download_to_drive(tmp_path)

        logger.info(f"Downloaded voice file: {tmp_path} ({voice.duration}s)")

        # Transcribe
        text = await transcribe_telegram_voice(tmp_path)

        # Clean up temp file
        try:
            tmp_path.unlink()
        except Exception:
            pass

        return text

    except Exception as e:
        logger.exception(f"Error downloading/transcribing voice: {e}")
        return None


if __name__ == "__main__":
    # Quick test
    import sys

    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) < 2:
        print("Usage: python transcribe.py <audio_file>")
        sys.exit(1)

    audio_file = Path(sys.argv[1])
    if not audio_file.exists():
        print(f"File not found: {audio_file}")
        sys.exit(1)

    async def main():
        text = await transcribe_audio(audio_file)
        if text:
            print(f"Transcription:\n{text}")
        else:
            print("Transcription failed")

    asyncio.run(main())
