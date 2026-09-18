#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required. On macOS: brew install uv" >&2
  exit 1
fi

echo "[gitlab-agent] installing editable user tool from: $ROOT"
uv tool install --editable "$ROOT" --force

CONFIG_DIR="${HOME}/.config/gitlab-agent"
CONFIG_FILE="${CONFIG_DIR}/.env"
mkdir -p "$CONFIG_DIR"
chmod 700 "$CONFIG_DIR"

if [[ ! -f "$CONFIG_FILE" ]]; then
  echo
  echo "[gitlab-agent] no global config yet."
  echo "Copy your working .env to:"
  echo "  $CONFIG_FILE"
  echo "Then run:"
  echo "  chmod 600 $CONFIG_FILE"
else
  chmod 600 "$CONFIG_FILE"
  echo "[gitlab-agent] using existing config: $CONFIG_FILE"
fi

echo
echo "Verify from any directory:"
echo "  actual-coder --help"
echo "  actual-coder config"
echo "  codingagent --help  # compatibility alias"
echo "  gitlab-agent --help"
