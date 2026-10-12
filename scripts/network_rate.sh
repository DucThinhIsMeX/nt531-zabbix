#!/usr/bin/env bash
set -euo pipefail
if [ "$#" -lt 3 ] || [ "$#" -gt 5 ]; then
  echo 'Run on C: sudo bash scripts/network_rate.sh INTERFACE IP_B RATE_KBIT [BURST_KB] [LATENCY_MS]'
  echo 'Example (500 kbps rate limit): sudo bash scripts/network_rate.sh eth0 192.168.1.102 500 32 50'; exit 2
fi
iface=$1
broker=$2
rate=$3
burst=${4:-32}
latency=${5:-50}
[[ "$iface" =~ ^[a-zA-Z0-9_.:-]+$ ]] || exit 2
[[ "$rate" =~ ^[0-9]+$ ]] && [ "$rate" -ge 10 ] && [ "$rate" -le 1000000 ] || exit 2
[[ "$burst" =~ ^[0-9]+$ ]] && [ "$burst" -ge 1 ] && [ "$burst" -le 1000 ] || exit 2
[[ "$latency" =~ ^[0-9]+$ ]] && [ "$latency" -ge 1 ] && [ "$latency" -le 1000 ] || exit 2
python3 -c 'import ipaddress,sys; ipaddress.IPv4Address(sys.argv[1])' "$broker"
ip link show dev "$iface" > /dev/null
state="/run/nt531-rate-${iface}"
if ls /run/nt531-*-"${iface}" 1>/dev/null 2>&1; then
  echo 'Lab rule already active on this interface. Reset first.'; exit 1
fi
existing=$(tc qdisc show dev "$iface")
if ! printf '%s\n' "$existing" | python3 -c 'import sys,re; s=sys.stdin.read(); rows=[x for x in s.splitlines() if " root " in x]; sys.exit(0 if rows and all(re.match(r"qdisc (mq|noqueue|fq_codel|pfifo_fast) 0:",x) for x in rows) else 1)'; then
  echo 'Existing custom qdisc detected; refusing to overwrite.'; exit 1
fi
printf '%s\n' "$existing" > "$state"
restore_on_error() { tc qdisc del dev "$iface" root 2>/dev/null || true; rm -f "$state"; }
trap restore_on_error ERR
tc qdisc replace dev "$iface" root handle 531: prio bands 3 priomap 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1
tc qdisc add dev "$iface" parent 531:3 handle 532: tbf rate "${rate}kbit" burst "${burst}k" latency "${latency}ms"
tc filter add dev "$iface" protocol ip parent 531: prio 1 u32 match ip dst "$broker/32" match ip protocol 6 0xff match ip dport 5672 0xffff flowid 531:3
tc filter add dev "$iface" protocol ip parent 531: prio 2 u32 match ip dst "$broker/32" match ip protocol 1 0xff flowid 531:3
trap - ERR
echo "Applied ${rate} kbit/s bandwidth limit (burst ${burst}k, latency ${latency}ms) on C egress to B AMQP + ICMP."
tc -s qdisc show dev "$iface"
echo "Reset: sudo bash scripts/network_reset.sh $iface"
