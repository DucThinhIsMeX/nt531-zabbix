import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from common import atomic_json, mean, utc


def measure_ping_baseline(target_ip, count=10):
    try:
        proc = subprocess.run(['ping', '-c', str(count), '-W', '2', target_ip],
                              capture_output=True, text=True, timeout=count * 2 + 5,
                              env={'LC_ALL': 'C', 'PATH': '/usr/bin:/bin'})
        times = [float(m) for m in re.findall(r'time[=<]([\d.]+)', proc.stdout)]
        loss_match = re.search(r'(\d+)% packet loss', proc.stdout)
        loss_pct = float(loss_match[1]) if loss_match else 0.0
        return {
            'samples': len(times),
            'min_ms': min(times) if times else None,
            'avg_ms': round(mean(times), 2) if times else None,
            'max_ms': max(times) if times else None,
            'packet_loss_pct': loss_pct
        }
    except Exception as error:
        return {'error': str(error)}


def run_iperf_baseline(server_ip, port=5201, duration=10):
    # 1. TCP test
    tcp_cmd = ['iperf3', '-c', server_ip, '-p', str(port), '-t', str(duration), '-J']
    tcp_res = subprocess.run(tcp_cmd, capture_output=True, text=True, timeout=duration + 10)
    if tcp_res.returncode != 0:
        raise RuntimeError(f"iperf3 TCP failed: {tcp_res.stderr or tcp_res.stdout}")
    tcp_data = json.loads(tcp_res.stdout)

    # 2. UDP test
    udp_cmd = ['iperf3', '-c', server_ip, '-p', str(port), '-u', '-b', '100M', '-t', str(duration), '-J']
    udp_res = subprocess.run(udp_cmd, capture_output=True, text=True, timeout=duration + 10)
    udp_data = json.loads(udp_res.stdout) if udp_res.returncode == 0 else {}

    # Extract metrics
    tcp_bps = tcp_data['end']['sum_received']['bits_per_second']
    tcp_mbps = round(tcp_bps / 1e6, 2)
    retransmits = tcp_data['end']['sum_sent'].get('retransmits', 0)

    udp_mbps = None
    jitter_ms = None
    udp_loss_pct = None
    if 'end' in udp_data and 'sum' in udp_data['end']:
        udp_sum = udp_data['end']['sum']
        udp_mbps = round(udp_sum.get('bits_per_second', 0) / 1e6, 2)
        jitter_ms = round(udp_sum.get('jitter_ms', 0), 3)
        udp_loss_pct = round(udp_sum.get('lost_percent', 0), 2)

    return {
        'tcp_throughput_mbps': tcp_mbps,
        'tcp_retransmits': retransmits,
        'udp_throughput_mbps': udp_mbps,
        'udp_jitter_ms': jitter_ms,
        'udp_loss_pct': udp_loss_pct
    }


def main():
    p = argparse.ArgumentParser(description='Measure baseline unshaped physical link capacity using iperf3 and ICMP')
    p.add_argument('--server-ip', required=True, help='Target server IP running iperf3 -s')
    p.add_argument('--port', type=int, default=5201, help='iperf3 port (default 5201)')
    p.add_argument('--duration', type=int, default=10, help='Duration per test in seconds (default 10)')
    p.add_argument('--output', default='data/baseline/link_baseline.json', help='Output JSON path')
    p.add_argument('--dry-run', action='store_true', help='Print commands without executing')
    a = p.parse_args()

    if a.dry_run:
        print(f"--- iperf3 Baseline Commands for target {a.server_ip} ---")
        print(f"# 1. Ensure server is running on target: iperf3 -s -p {a.port}")
        print(f"# 2. TCP baseline: iperf3 -c {a.server_ip} -p {a.port} -t {a.duration} -J")
        print(f"# 3. UDP baseline: iperf3 -c {a.server_ip} -p {a.port} -u -b 100M -t {a.duration} -J")
        print(f"# 4. ICMP baseline: ping -c 10 {a.server_ip}")
        return

    print(f"Measuring raw baseline link capacity to {a.server_ip}:{a.port}...")
    print("1. Running ICMP ping baseline (10 packets)...", flush=True)
    ping_stats = measure_ping_baseline(a.server_ip, count=10)

    print("2. Running iperf3 TCP & UDP baseline...", flush=True)
    try:
        iperf_stats = run_iperf_baseline(a.server_ip, port=a.port, duration=a.duration)
    except Exception as err:
        print(f"Error executing iperf3: {err}")
        print("Tip: Make sure 'iperf3 -s' is running on the target machine.")
        sys.exit(1)

    result = {
        'measured_at_utc': utc(),
        'target_ip': a.server_ip,
        'duration_seconds': a.duration,
        'ping': ping_stats,
        'iperf': iperf_stats,
        'note': 'Clean physical baseline prior to applying any netem/tbf shaping'
    }

    out_path = Path(a.output)
    atomic_json(out_path, result)

    print(f"\n--- BASELINE LINK CAPACITY REPORT ({a.server_ip}) ---")
    print(f"  ICMP Base RTT:       min={ping_stats.get('min_ms')} ms, avg={ping_stats.get('avg_ms')} ms, max={ping_stats.get('max_ms')} ms")
    print(f"  ICMP Base Loss:      {ping_stats.get('packet_loss_pct')}%")
    print(f"  TCP Raw Capacity:    {iperf_stats['tcp_throughput_mbps']} Mbps (retransmits: {iperf_stats['tcp_retransmits']})")
    if iperf_stats['udp_throughput_mbps']:
        print(f"  UDP Capacity/Jitter: {iperf_stats['udp_throughput_mbps']} Mbps, Jitter: {iperf_stats['udp_jitter_ms']} ms, Loss: {iperf_stats['udp_loss_pct']}%")
    print(f"Saved baseline report to: {out_path}\n")


if __name__ == '__main__':
    main()
