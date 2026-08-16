#!/usr/bin/env python3
"""Local microphone speech-to-text using Whisper."""
import os
import sys
import tempfile
import wave
import logging
from pathlib import Path

# Suppress ALSA/JACK warnings
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
from ctypes import CFUNCTYPE, c_char_p, c_int, cdll

def _suppress_alsa_errors():
    try:
        asound = cdll.LoadLibrary('libasound.so.2')
        c_error_handler = CFUNCTYPE(None, c_char_p, c_int, c_char_p, c_int, c_char_p)
        asound.snd_lib_error_set_handler(c_error_handler(lambda *_: None))
    except:
        pass

_suppress_alsa_errors()

logging.basicConfig(level=logging.INFO, format='%(message)s')
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# Recording settings
RATE = 16000
CHANNELS = 1
CHUNK = 1024


def record_audio(duration: float = 5.0) -> Path:
    """Record audio from microphone."""
    import pyaudio

    p = pyaudio.PyAudio()

    stream = p.open(
        format=pyaudio.paInt16,
        channels=CHANNELS,
        rate=RATE,
        input=True,
        frames_per_buffer=CHUNK
    )

    logger.info(f"Recording for {duration}s... (speak now)")

    frames = []
    for _ in range(int(RATE / CHUNK * duration)):
        data = stream.read(CHUNK)
        frames.append(data)

    logger.info("Recording finished.")

    stream.stop_stream()
    stream.close()
    p.terminate()

    # Save to temp file
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    with wave.open(tmp.name, 'wb') as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(RATE)
        wf.writeframes(b''.join(frames))

    return Path(tmp.name)


def transcribe(audio_path: Path) -> str:
    """Transcribe audio file using Whisper."""
    from faster_whisper import WhisperModel

    logger.info("Loading Whisper model...")
    model = WhisperModel("base", device="cpu", compute_type="int8")

    logger.info("Transcribing...")
    segments, info = model.transcribe(str(audio_path), beam_size=5)

    text = " ".join(seg.text for seg in segments).strip()
    return text


def main():
    duration = float(sys.argv[1]) if len(sys.argv) > 1 else 5.0

    print(f"\n{'='*50}")
    print("Local Speech-to-Text")
    print(f"{'='*50}\n")

    audio_path = record_audio(duration)

    try:
        text = transcribe(audio_path)
        print(f"\n{'='*50}")
        print("TRANSCRIPTION:")
        print(f"{'='*50}")
        print(text)
        print(f"{'='*50}\n")
    finally:
        audio_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
