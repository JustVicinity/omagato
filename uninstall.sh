#!/usr/bin/env bash
set -euo pipefail
source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=scripts/path-guards.sh
source "$source_dir/scripts/path-guards.sh"

plugin_id="io.github.justvicinity.omagato"
unit="$HOME/.config/systemd/user/omagato.service"
venv_dir="${XDG_DATA_HOME:-$HOME/.local/share}/omagato/venv"
config_dir="${XDG_CONFIG_HOME:-$HOME/.config}/omarchy-elgato"
guard_managed_path "$unit" omagato.service
guard_managed_path "$venv_dir" venv
guard_managed_path "$config_dir" omarchy-elgato

if [[ $# -gt 1 ]] || [[ $# -eq 1 && "$1" != "--purge-config" ]]; then
  echo "Usage: ./uninstall.sh [--purge-config]" >&2
  exit 2
fi

omarchy plugin disable "$plugin_id" || true
if [[ -f "$unit" ]] && grep -q '^# Managed by OmaGato$' "$unit"; then
  systemctl --user disable --now omagato.service || true
  rm "$unit"
  systemctl --user daemon-reload
fi
rm -rf "$venv_dir"
if [[ ${1:-} == "--purge-config" ]]; then
  rm -rf "$config_dir"
fi
echo "OmaGato service removed. Remove the plugin checkout with Omarchy or your file manager."
