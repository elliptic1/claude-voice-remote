#!/usr/bin/env python3
"""Push-to-talk STT - press hotkey to start, press again to stop and transcribe."""
import os
import sys
import signal
import tempfile
import wave
import subprocess
from pathlib import Path

# Suppress ALSA warnings
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
from ctypes import CFUNCTYPE, c_char_p, c_int, cdll
try:
    asound = cdll.LoadLibrary('libasound.so.2')
    c_error_handler = CFUNCTYPE(None, c_char_p, c_int, c_char_p, c_int, c_char_p)
    asound.snd_lib_error_set_handler(c_error_handler(lambda *_: None))
except:
    pass

STATE_FILE = Path("/tmp/stt_recording.pid")
AUDIO_FILE = Path("/tmp/stt_recording.wav")

RATE = 16000
CHANNELS = 1
CHUNK = 1024


def notify(title: str, msg: str, timeout: int = 3000):
    """Send desktop notification."""
    # Use -r to replace previous STT notifications instead of stacking
    subprocess.run(["notify-send", "-t", str(timeout), "-r", "9999", title, msg],
                   capture_output=True)


def copy_to_clipboard(text: str):
    """Copy text to clipboard."""
    # Try xsel first (more reliable for our use case)
    try:
        subprocess.run(["xsel", "--clipboard", "--input"],
                       input=text.encode(), capture_output=True, check=True)
        return
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass

    # Fall back to xclip
    try:
        subprocess.run(
            ["xclip", "-selection", "clipboard"],
            input=text.encode(),
            capture_output=True
        )
    except FileNotFoundError:
        pass


def auto_paste(text: str):
    """Type text using ydotool with sudo."""
    try:
        import time
        # Small delay to let user release the hotkey
        time.sleep(0.5)
        # Run ydotool as root via sudo (passwordless for todd)
        subprocess.run(["sudo", "ydotool", "type", text],
                       capture_output=True, timeout=10)
    except Exception:
        pass


def start_recording():
    """Start recording in background."""
    import pyaudio

    # Fork to background
    pid = os.fork()
    if pid > 0:
        # Parent - save PID and exit
        STATE_FILE.write_text(str(pid))
        notify("🎤 Recording", "Press hotkey again to stop")
        sys.exit(0)

    # Child - do the recording
    os.setsid()

    p = pyaudio.PyAudio()
    stream = p.open(
        format=pyaudio.paInt16,
        channels=CHANNELS,
        rate=RATE,
        input=True,
        frames_per_buffer=CHUNK
    )

    frames = []

    def save_and_exit(signum, frame):
        stream.stop_stream()
        stream.close()
        p.terminate()

        with wave.open(str(AUDIO_FILE), 'wb') as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)
            wf.setframerate(RATE)
            wf.writeframes(b''.join(frames))
        sys.exit(0)

    signal.signal(signal.SIGTERM, save_and_exit)
    signal.signal(signal.SIGINT, save_and_exit)

    # Record until killed
    while True:
        try:
            data = stream.read(CHUNK, exception_on_overflow=False)
            frames.append(data)
        except:
            break


def stop_and_transcribe():
    """Stop recording and transcribe."""
    if not STATE_FILE.exists():
        notify("⚠ Not Recording", "Press hotkey to start recording first")
        return

    pid = int(STATE_FILE.read_text().strip())
    STATE_FILE.unlink()

    # Kill the recording process
    try:
        os.kill(pid, signal.SIGTERM)
        os.waitpid(pid, 0)
    except (ProcessLookupError, ChildProcessError):
        pass

    # Wait for audio file
    import time
    for _ in range(10):
        if AUDIO_FILE.exists() and AUDIO_FILE.stat().st_size > 1000:
            break
        time.sleep(0.1)

    if not AUDIO_FILE.exists():
        notify("⚠ STT Failed", "No audio recorded")
        return

    notify("⏳ Transcribing...", "Please wait")

    # Transcribe
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel("base", device="cpu", compute_type="int8")
        segments, info = model.transcribe(str(AUDIO_FILE), beam_size=5)
        text = " ".join(seg.text for seg in segments).strip()
    except Exception as e:
        notify("⚠ STT Failed", str(e))
        return
    finally:
        AUDIO_FILE.unlink(missing_ok=True)

    if text:
        copy_to_clipboard(text)
        auto_paste(text)
        # Truncate for notification if too long
        display = text[:200] + "..." if len(text) > 200 else text
        notify("✓ Transcribed", display, timeout=3000)
    else:
        notify("⚠ No Speech", "Nothing detected")


def main():
    if STATE_FILE.exists():
        stop_and_transcribe()
    else:
        start_recording()


if __name__ == "__main__":
    main()
