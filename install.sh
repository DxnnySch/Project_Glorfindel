#!/usr/bin/env bash
# Projekt Glorfindel – Installation (macOS/Linux)
set -e
cd "$(dirname "$0")"
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
command -v ffmpeg >/dev/null || echo "Bitte ffmpeg installieren (z. B. 'brew install ffmpeg' oder 'apt install ffmpeg')."
export PATH="$HOME/.local/bin:$PATH"
uv venv .venv
uv pip install -e "."
read -r -p "Lokales Whisper installieren? [J/n] " a
[ "$a" = "n" ] || uv pip install faster-whisper
[ -f .env ] || cp .env.example .env
echo "Fertig. Start mit ./start.sh"
