#!/usr/bin/env bash
set -euo pipefail
[ "$#" -eq 1 ] || { echo 'sudo bash scripts/network_reset.sh INTERFACE'; exit 2; }
iface=$1
[[ "$iface" =~ ^[a-zA-Z0-9_.:-]+$ ]] || exit 2
state="/run/nt531-delay-${iface}"
[ -e "$state" ] || { echo 'No lab rule marker; refusing to delete another qdisc.'; exit 1; }
if tc qdisc show dev "$iface" | grep -q 'qdisc prio 531:'; then
  tc qdisc del dev "$iface" root
  rm -f "$state"
  echo 'Lab qdisc removed. Linux default restored; verify ping baseline.'
else
  echo 'Lab qdisc not found. Inspect manually; marker preserved.'; exit 1
fi
