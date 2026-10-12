#!/usr/bin/env bash
set -euo pipefail
if [ "$#" -ne 3 ]; then
  echo 'Run on C: sudo bash scripts/network_delay.sh INTERFACE IP_B DELAY_MS'; exit 2
fi
iface=$1
broker=$2
delay=$3
[[ "$iface" =~ ^[a-zA-Z0-9_.:-]+$ ]] || exit 2
[[ "$delay" =~ ^[0-9]+$ ]] && [ "$delay" -le 1000 ] || exit 2
python3 -c 'import ipaddress,sys; ipaddress.IPv4Address(sys.argv[1])' "$broker"
ip link show dev "$iface" > /dev/null
state="/run/nt531-delay-${iface}"
if [ -e "$state" ]; then echo 'Rule already active. Reset first.'; exit 1; fi
existing=$(tc qdisc show dev "$iface")
if ! printf '%s\n' "$existing" | python3 -c 'import sys,re; s=sys.stdin.read(); rows=[x for x in s.splitlines() if " root " in x]; sys.exit(0 if rows and all(re.match(r"qdisc (mq|noqueue|fq_codel|pfifo_fast) 0:",x) for x in rows) else 1)'; then
  echo 'Existing custom qdisc detected; refusing to overwrite.'; exit 1
fi
printf '%s\n' "$existing" > "$state"
restore_on_error() { tc qdisc del dev "$iface" root 2>/dev/null || true; rm -f "$state"; }
trap restore_on_error ERR
tc qdisc replace dev "$iface" root handle 531: prio bands 3 priomap 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1
tc qdisc add dev "$iface" parent 531:3 handle 532: netem delay "${delay}ms"
tc filter add dev "$iface" protocol ip parent 531: prio 1 u32 match ip dst "$broker/32" match ip protocol 6 0xff match ip dport 5672 0xffff flowid 531:3
tc filter add dev "$iface" protocol ip parent 531: prio 2 u32 match ip dst "$broker/32" match ip protocol 1 0xff flowid 531:3
trap - ERR
echo "Applied ${delay} ms on C egress to B AMQP + ICMP. Other ports default to unshaped band."
tc -s qdisc show dev "$iface"
echo "Reset: sudo bash scripts/network_reset.sh $iface"
