#!/bin/bash
# Push-to-talk STT hotkey wrapper
export DISPLAY=:0
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
export XDG_RUNTIME_DIR=/run/user/1000
export PULSE_RUNTIME_PATH=/run/user/1000/pulse
export HOME=/home/todd

exec /media/todd/androiddev/workspace/claude-voice-remote/venv/bin/python \
     /media/todd/androiddev/workspace/claude-voice-remote/stt_toggle.py
