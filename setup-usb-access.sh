#!/usr/bin/env bash
set -euo pipefail
source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
sudo install -m 0644 "$source_dir/udev/70-omarchy-elgato.rules" /etc/udev/rules.d/70-omarchy-elgato.rules
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=usb --attr-match=idVendor=0fd9
echo "USB-Regel aktiv. Stream Deck bei Bedarf kurz neu verbinden."
