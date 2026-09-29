#!/usr/bin/env bash
set -euo pipefail

source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
plugin_id="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["id"])' "$source_dir/manifest.json")"
target="$HOME/.config/omarchy/plugins/$plugin_id"
venv_dir="${XDG_DATA_HOME:-$HOME/.local/share}/omagato/venv"
unit="$HOME/.config/systemd/user/omagato.service"

if [[ "$source_dir" != "$target" ]]; then
  if [[ -d "$target/.git" ]]; then
    echo "Existing Git checkout detected. Run omarchy plugin update, then its install.sh." >&2
    exit 1
  fi
  mkdir -p "$target"
  # Theme artwork is generated and owned by this plugin. Clear older files
  # (including formats no longer shipped) before installing the current pack.
  rm -rf "$target/assets/icon-themes"
  for item in ActionChip.qml BarWidget.qml CameraPreview.qml IconGallery.qml PickerRow.qml UiField.qml UiSelect.qml \
              PrompterService.qml TeleprompterOverlay.qml LICENSE README.md manifest.json \
              requirements.txt install.sh setup-usb-access.sh uninstall.sh udev bin elgato assets scripts docs; do
    cp -a "$source_dir/$item" "$target/"
  done
fi

if [[ ! -x "$venv_dir/bin/python" ]]; then
  python3 -m venv "$venv_dir"
fi
"$venv_dir/bin/python" -m pip install --disable-pip-version-check -r "$target/requirements.txt"

mkdir -p "$(dirname "$unit")"
if [[ -e "$unit" ]] && ! grep -q '^# Managed by OmaGato$' "$unit"; then
  echo "Refusing to replace an unrelated systemd unit: $unit" >&2
  exit 1
fi
cat > "$unit" <<UNIT
# Managed by OmaGato
[Unit]
Description=OmaGato Stream Deck controller
After=graphical-session.target

[Service]
Type=simple
ExecStart=%h/.config/omarchy/plugins/$plugin_id/bin/elgatoctl daemon
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
UNIT
systemctl --user daemon-reload
systemctl --user enable --now omagato.service
systemctl --user restart omagato.service
omarchy plugin enable "$plugin_id"
echo "OmaGato is ready. Your device configuration stays in ~/.config/omarchy-elgato/."
