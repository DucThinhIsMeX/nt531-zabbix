#!/usr/bin/env bash
set -euo pipefail
[ "$#" -eq 1 ] || { echo 'sudo bash scripts/network_reset.sh INTERFACE'; exit 2; }
iface=$1
[[ "$iface" =~ ^[a-zA-Z0-9_.:-]+$ ]] || exit 2
markers=$(compgen -G "/run/nt531-*-${iface}" || true)
if [ -z "$markers" ]; then
  echo 'No lab rule marker found; refusing to delete an unmanaged qdisc.'; exit 1
fi
if tc qdisc show dev "$iface" | grep -q '531:'; then
  tc qdisc del dev "$iface" root
  rm -f /run/nt531-*-"${iface}"
  echo 'Lab qdisc removed. Linux default restored; verify ping baseline.'
else
  echo 'Lab qdisc not found. Inspect manually; marker preserved.'; exit 1
fi
