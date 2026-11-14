#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Run this setup script once with sudo." >&2
  exit 1
fi

target_user=${SUDO_USER:-}
if [[ -z "$target_user" || "$target_user" == "root" ]]; then
  echo "Run with sudo from your desktop user so the script can grant device access to that account." >&2
  exit 1
fi

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
rule_file="$script_dir/../udev/99-x11se-hidraw.rules"

if ! getent group input >/dev/null; then
  groupadd input
fi

install -Dm644 "$rule_file" /etc/udev/rules.d/99-x11se-hidraw.rules

if [[ " $(id -nG "$target_user") " != *" input "* ]]; then
  usermod -aG input "$target_user"
  relogin=true
else
  relogin=false
fi

udevadm control --reload-rules
udevadm trigger --subsystem-match=hidraw

echo "Installed the X11SE hidraw rule for $target_user. Reconnect the receiver."
if [[ "$relogin" == true ]]; then
  echo "The account was added to the input group; log out and back in before using the plugin."
fi
