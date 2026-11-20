#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Run this setup script once with sudo." >&2
  exit 1
fi

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
rule_file="$script_dir/../udev/70-x11se-hidraw.rules"

# Clean up legacy 99- rule if present
rm -f /etc/udev/rules.d/99-x11se-hidraw.rules

install -Dm644 "$rule_file" /etc/udev/rules.d/70-x11se-hidraw.rules

udevadm control --reload-rules
udevadm trigger --subsystem-match=hidraw

echo "Installed the X11SE hidraw rule. Reconnect the receiver or USB cable."
