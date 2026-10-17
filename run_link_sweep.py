"""
NT531 - Script thực nghiệm đo hiệu năng liên kết mạng, đo bằng iperf3 + ping,
tự áp điều kiện mạng bằng tc/netem/tbf. Chạy TRÊN MÁY C (máy tạo nhiễu).

Ba kịch bản (scenario):
  - loss_tcp          : KB1 - throughput TCP theo tỷ lệ mất gói (đối chiếu Mathis)
  - utilization_delay : KB2 - độ trễ theo độ hữu dụng (đối chiếu M/M/1), lặp nhiều lần
  - bandwidth_cap     : KB3 - hiệu suất throughput theo trần băng thông (tbf)

Lệnh đã dùng trong đồ án (server-ip là IP CÁP của máy B, ví dụ 10.10.0.1):
  python run_link_sweep.py --scenario loss_tcp --server-ip 10.10.0.1 --duration 90 --loss-cap 50 --base-delay 5
  python run_link_sweep.py --scenario utilization_delay --server-ip 10.10.0.1 --link-cap 2 --duration 12 --repeats 3
  python run_link_sweep.py --scenario bandwidth_cap --server-ip 10.10.0.1 --duration 15
"""
import argparse, csv, json, math, re, subprocess, time, threading, statistics
from pathlib import Path
from common import atomic_json, mean, utc


def tc_reset(iface):
    subprocess.run(['sudo', 'tc', 'qdisc', 'del', 'dev', iface, 'root'], capture_output=True, text=True)


def tc_apply(iface, spec):
    r = subprocess.run(['sudo', 'tc', 'qdisc', 'replace', 'dev', iface, 'root'] + spec,
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  [tc ERR] {r.stderr.strip()}", flush=True)
        return False
    return True


def tbf_spec(c):
    return ['tbf', 'rate', f'{c}mbit', 'burst', '32kbit', 'latency', '400ms']


def verify_qdisc(iface):
    return subprocess.run(['tc', 'qdisc', 'show', 'dev', iface], capture_output=True, text=True).stdout.strip()


def measure(server_ip, port, duration, is_udp=False, bandwidth_mbps=None):
    """Chạy iperf3 ở nền và ping ĐỒNG THỜI trong lúc có tải, rồi gộp kết quả."""
    cmd = ['iperf3', '-c', server_ip, '-p', str(port), '-t', str(duration), '-J']
    if is_udp:
        cmd += ['-u', '-b', f"{bandwidth_mbps}M" if bandwidth_mbps else "10M"]
    ip = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    time.sleep(0.5)
    pc = max(5, int((duration - 1) / 0.2))
    pr = {}

    def dp():
        try:
            p = subprocess.run(['ping', '-n', '-i', '0.2', '-c', str(pc), '-W', '2', server_ip],
                               capture_output=True, text=True, timeout=duration + 10,
                               env={'LC_ALL': 'C', 'PATH': '/usr/bin:/bin'})
            t = [float(m) for m in re.findall(r'time[=<]([\d.]+)', p.stdout)]
            lm = re.search(r'(\d+)% packet loss', p.stdout)
            pr['rtt'] = round(mean(t), 2) if t else None
            pr['loss'] = float(lm[1]) if lm else None
        except Exception:
            pr['rtt'] = None
            pr['loss'] = None

    th = threading.Thread(target=dp)
    th.start()
    out, _ = ip.communicate(timeout=duration + 15)
    th.join()
    st = None
    if ip.returncode == 0:
        try:
            d = json.loads(out)
            if is_udp:
                s = d['end']['sum']
                st = {'throughput_mbps': round(s.get('bits_per_second', 0) / 1e6, 2)}
            else:
                st = {'throughput_mbps': round(d['end']['sum_received']['bits_per_second'] / 1e6, 2),
                      'retransmits': d['end']['sum_sent'].get('retransmits', 0)}
        except Exception:
            st = None
    return st, pr.get('rtt'), pr.get('loss')


def run_utilization_delay_sweep(iface, server_ip, port, link_cap, duration, repeats=3):
    """KB2: netem rate + limit (hàng đợi hữu hạn), quét ρ tới vượt trần, lặp repeats lần."""
    rhos = [0.3, 0.5, 0.7, 0.85, 0.9, 0.95, 0.97, 0.99, 1.0, 1.02, 1.05, 1.1, 1.3]
    rows = []
    ql = 100  # giới hạn độ dài hàng đợi (gói)
    for rho in rhos:
        off = round(rho * link_cap, 2)
        mm1 = round(2.0 / max(0.05, (1.0 - min(rho, 0.98))), 2)
        rtts, thrs, los = [], [], []
        for k in range(repeats):
            tc_reset(iface)
            tc_apply(iface, ['netem', 'rate', f'{link_cap}mbit', 'limit', str(ql)])
            print(f"  rho={rho} offered={off} Mbps lan {k+1}/{repeats}", flush=True)
            st, rtt, loss = measure(server_ip, port, duration, is_udp=True, bandwidth_mbps=off)
            if rtt is not None: rtts.append(rtt)
            if st: thrs.append(st['throughput_mbps'])
            if loss is not None: los.append(loss)
            time.sleep(2)
        a = lambda x: round(statistics.mean(x), 2) if x else None
        s = lambda x: round(statistics.pstdev(x), 2) if len(x) > 1 else 0.0
        rows.append({'rho_target': rho, 'offered_mbps': off, 'link_cap_mbps': link_cap,
                     'achieved_mbps_mean': a(thrs), 'rtt_ms_mean': a(rtts), 'rtt_ms_std': s(rtts),
                     'rtt_samples': len(rtts), 'mm1_theoretical_rtt_ms': mm1, 'packet_loss_pct_mean': a(los)})
    tc_reset(iface)
    return rows


def run_loss_tcp_sweep(iface, server_ip, port, duration, loss_cap=50.0, base_delay=5.0):
    """KB1: cố định băng thông loss_cap + độ trễ nền base_delay, quét tỷ lệ mất gói."""
    losses = [0.0, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0]
    rows = []
    mss = 1460
    brtt = (2 * base_delay) / 1000.0  # RTT nền (giây)
    for p in losses:
        tc_reset(iface)
        spec = ['netem', 'delay', f'{base_delay}ms', 'rate', f'{loss_cap}mbit']
        if p > 0:
            spec += ['loss', f'{p}%']
        tc_apply(iface, spec)
        print(f"  loss={p}% ({verify_qdisc(iface)})", flush=True)
        mathis = loss_cap if p == 0 else round(min(loss_cap,
                 ((mss * 8.0) / (brtt * math.sqrt(p / 100.0)) * 1.22) / 1e6), 2)
        st, rtt, _ = measure(server_ip, port, duration, is_udp=False)
        rows.append({'netem_loss_pct': p, 'measured_tcp_mbps': st['throughput_mbps'] if st else None,
                     'mathis_theoretical_mbps': mathis, 'retransmits': st['retransmits'] if st else None,
                     'rtt_ms': rtt})
        time.sleep(2)
    tc_reset(iface)
    return rows


def run_bandwidth_cap_sweep(iface, server_ip, port, duration):
    """KB3: quét trần băng thông bằng tbf, đo throughput đạt được và hiệu suất."""
    caps = [1.0, 2.0, 5.0, 10.0, 20.0, 50.0]
    rows = []
    for c in caps:
        tc_reset(iface)
        tc_apply(iface, tbf_spec(c))
        print(f"  cap={c} Mbps ({verify_qdisc(iface)})", flush=True)
        st, rtt, _ = measure(server_ip, port, duration, is_udp=False)
        ach = st['throughput_mbps'] if st else None
        eff = round((ach / c) * 100, 1) if (ach is not None and c > 0) else None
        rows.append({'tbf_cap_mbps': c, 'measured_tcp_mbps': ach, 'efficiency_pct': eff, 'rtt_ms': rtt})
        time.sleep(2)
    tc_reset(iface)
    return rows


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--scenario', required=True, choices=['utilization_delay', 'loss_tcp', 'bandwidth_cap'])
    p.add_argument('--server-ip', required=True)
    p.add_argument('--iface', default='eth0')
    p.add_argument('--port', type=int, default=5201)
    p.add_argument('--link-cap', type=float, default=10.0)
    p.add_argument('--duration', type=int, default=15)
    p.add_argument('--repeats', type=int, default=3)
    p.add_argument('--loss-cap', type=float, default=50.0)
    p.add_argument('--base-delay', type=float, default=5.0)
    p.add_argument('--output-dir', default='data/link_sweeps')
    a = p.parse_args()
    out = Path(a.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    print("Priming sudo...")
    subprocess.run(['sudo', '-v'])
    print(f"\n=== {a.scenario.upper()} === {a.server_ip}:{a.port} via {a.iface}")
    try:
        if a.scenario == 'utilization_delay':
            data = run_utilization_delay_sweep(a.iface, a.server_ip, a.port, a.link_cap, a.duration, a.repeats)
        elif a.scenario == 'loss_tcp':
            data = run_loss_tcp_sweep(a.iface, a.server_ip, a.port, a.duration, a.loss_cap, a.base_delay)
        else:
            data = run_bandwidth_cap_sweep(a.iface, a.server_ip, a.port, a.duration)
    finally:
        tc_reset(a.iface)
    jp = out / f"link_sweep_{a.scenario}.json"
    cp = out / f"link_sweep_{a.scenario}.csv"
    atomic_json(jp, {'scenario': a.scenario, 'mode': 'live', 'measured_at_utc': utc(), 'results': data})
    if data:
        with cp.open('w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=list(data[0].keys()))
            w.writeheader()
            w.writerows(data)
    print(f"\nSaved {jp}\n--- RESULTS ---")
    hs = list(data[0].keys())
    line = " | ".join(f"{h:<18}" for h in hs)
    print(line)
    print("-" * len(line))
    for r in data:
        print(" | ".join(f"{str(r[h]):<18}" for h in hs))


if __name__ == '__main__':
    main()
