#!/usr/bin/env bash
set -euo pipefail

# Configuration
APP_NAME="hyprsunset_tray"
INSTALL_DIR="$HOME/.local/bin/$APP_NAME"
VENV_DIR="$INSTALL_DIR/.venv"
REPO_URL="https://github.com/laisoJS/hyprsunset-tray.git"
HYPR_CONF="$HOME/.config/hypr/hyprland.conf"
EXEC_LINE="exec-once = $VENV_DIR/bin/python $INSTALL_DIR/hyprsunset-tray.py &"

echo "🚀 Installing $APP_NAME..."

if [ -d "$INSTALL_DIR" ]; then
    echo "⚠️  $APP_NAME seems already installed at $INSTALL_DIR"
    read -rp "Do you want to reinstall it? [y/N]: " REINSTALL
    if [[ ! "$REINSTALL" =~ ^[Yy]$ ]]; then
        echo "Installation aborted."
        exit 0
    fi
    rm -rf "$INSTALL_DIR"
fi

if [ "${XDG_SESSION_TYPE:-}" = "x11" ]; then
    echo "❌  $APP_NAME only works on Wayland. Detected X11 session. Aborting."
    exit 1
fi

git clone "$REPO_URL" "$INSTALL_DIR"

python3 -m venv "$VENV_DIR"

source "$VENV_DIR/bin/activate"
pip install --upgrade pip
pip install PyQt6

# Make main script executable
chmod +x "$INSTALL_DIR/hyprsunset-tray.py"

if [ -f "$HYPR_CONF" ]; then
  read -rp "Do you want to enable autostart? [y/N]:" AUTOSTART
  if [[ "$AUTOSTART" =~ ^[Yy]$ ]]; then
    if grep -Fxq "$EXEC_LINE" "$HYPR_CONF"; then
      echo "ℹ️  Autostart entry already exists in $HYPR_CONF"
    fi
    echo "$EXEC_LINE" >> "$HYPR_CONF"
    echo "✅ Autostart line added to $HYPR_CONF"
  fi
else
  echo "⚠️  Could not find $HYPR_CONF — skipping autostart setup."
fi

echo "✅ $APP_NAME installed successfully!"
echo "You can manually start it with:"
echo "   $VENV_DIR/bin/python $INSTALL_DIR/hyprsunset-tray.py"

echo "▶️  Launching $APP_NAME..."
nohup "$VENV_DIR/bin/python" "$INSTALL_DIR/hyprsunset-tray.py" >/dev/null 2>&1 &
