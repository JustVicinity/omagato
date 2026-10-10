#!/usr/bin/env bash
set -u
source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
case "${1:-}" in
  install) bash "$source_dir/install.sh"; result=$? ;;
  usb) bash "$source_dir/setup-usb-access.sh"; result=$? ;;
  *) exit 2 ;;
esac
if [[ "$result" -ne 0 ]]; then
  echo "Setup failed. Review the message above before trying again."
else
  echo "Setup complete. Refresh OmaGato to check your devices."
fi
read -r -p "Press Enter to close. " _reply
exit "$result"
