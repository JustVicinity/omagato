#!/usr/bin/env bash
set -euo pipefail
umask 077

source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
plugin_id="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["id"])' "$source_dir/manifest.json")"
if [[ "$plugin_id" != "io.github.justvicinity.omagato" ]]; then
  echo "Unexpected plugin id; refusing installation." >&2
  exit 1
fi
# shellcheck source=scripts/path-guards.sh
source "$source_dir/scripts/path-guards.sh"
target="$HOME/.config/omarchy/plugins/$plugin_id"
venv_dir="${XDG_DATA_HOME:-$HOME/.local/share}/omagato/venv"
unit="$HOME/.config/systemd/user/omagato.service"
guard_managed_path "$target" "$plugin_id"
guard_managed_path "$venv_dir" venv
guard_managed_path "$unit" omagato.service
guard_managed_path "$target/assets/icon-themes" icon-themes
if [[ -e "$unit" ]] && ! grep -q '^# Managed by OmaGato$' "$unit"; then
  echo "Refusing to replace an unrelated systemd unit: $unit" >&2
  exit 1
fi

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
              PrompterService.qml TeleprompterOverlay.qml LICENSE README.md SECURITY.md CHANGELOG.md manifest.json \
              requirements.txt install.sh setup-usb-access.sh uninstall.sh udev bin elgato assets scripts docs; do
    cp -a "$source_dir/$item" "$target/"
  done
fi

if [[ ! -x "$venv_dir/bin/python" ]]; then
  python3 -m venv "$venv_dir"
fi
PIP_CONFIG_FILE=/dev/null "$venv_dir/bin/python" -m pip --isolated install --index-url https://pypi.org/simple \
  --only-binary=:all: --require-hashes --disable-pip-version-check -r "$target/requirements.txt"

mkdir -p "$(dirname "$unit")"
unit_tmp="$(mktemp "${unit}.XXXXXX")"
trap 'rm -f -- "$unit_tmp"' EXIT
cat > "$unit_tmp" <<UNIT
# Managed by OmaGato
[Unit]
Description=OmaGato Stream Deck controller
After=graphical-session.target
StartLimitIntervalSec=60
StartLimitBurst=5

[Service]
Type=simple
ExecStart=%h/.config/omarchy/plugins/$plugin_id/bin/elgatoctl daemon
Restart=on-failure
RestartSec=3
UMask=0077
MemoryHigh=384M
MemoryMax=512M
TasksMax=256

[Install]
WantedBy=default.target
UNIT
mv -T -- "$unit_tmp" "$unit"
systemctl --user daemon-reload
systemctl --user enable --now omagato.service
systemctl --user restart omagato.service
omarchy plugin enable "$plugin_id"
echo "OmaGato is ready. Your device configuration stays in ~/.config/omarchy-elgato/."
