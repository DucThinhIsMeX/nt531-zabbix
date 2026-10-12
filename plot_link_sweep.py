import argparse
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def plot_all_link_sweeps(input_dir, output_path):
    dir_path = Path(input_dir)
    util_file = dir_path / 'link_sweep_utilization_delay.json'
    loss_file = dir_path / 'link_sweep_loss_tcp.json'
    cap_file = dir_path / 'link_sweep_bandwidth_cap.json'

    fig, axes = plt.subplots(1, 3, figsize=(18, 5.5))
    (ax1, ax2, ax3) = axes

    # 1. Utilization vs Delay (M/M/1 Model Validation)
    if util_file.exists():
        data = json.loads(util_file.read_text(encoding='utf-8'))['results']
        rhos = [r['rho_target'] for r in data]
        rtt_measured = [r['rtt_ms'] for r in data]
        mm1_theory = [r['mm1_theoretical_rtt_ms'] for r in data]

        ax1.plot(rhos, mm1_theory, 'r--', label=r'M/M/1 Model: $W = \frac{T_0}{1 - \rho}$', linewidth=2)
        ax1.plot(rhos, rtt_measured, 'b-o', label='Measured UDP Delay (RTT)', linewidth=2)
        ax1.set_title('Link Utilization vs Delay (M/M/1 Validation)')
        ax1.set_xlabel('Link Utilization (rho = Throughput / C)')
        ax1.set_ylabel('Queueing Delay / RTT (ms)')
        ax1.grid(True, alpha=0.3)
        ax1.legend()
    else:
        ax1.text(0.5, 0.5, 'Run: run_link_sweep.py --scenario utilization_delay', ha='center')

    # 2. Packet Loss vs TCP Throughput (Mathis Model Validation)
    if loss_file.exists():
        data = json.loads(loss_file.read_text(encoding='utf-8'))['results']
        losses = [r['netem_loss_pct'] for r in data]
        tcp_measured = [r['measured_tcp_mbps'] for r in data]
        mathis_theory = [r['mathis_theoretical_mbps'] for r in data]

        ax2.plot(losses, mathis_theory, 'r--', label=r'Mathis Formula: $\propto \frac{1}{\sqrt{p}}$', linewidth=2)
        ax2.plot(losses, tcp_measured, 'g-s', label='Measured TCP Throughput', linewidth=2)
        ax2.set_title('Packet Loss vs TCP Throughput (Mathis Model)')
        ax2.set_xlabel('Netem Packet Loss (%)')
        ax2.set_ylabel('TCP Throughput (Mbps)')
        ax2.grid(True, alpha=0.3)
        ax2.legend()
    else:
        ax2.text(0.5, 0.5, 'Run: run_link_sweep.py --scenario loss_tcp', ha='center')

    # 3. Bandwidth Cap Sweep
    if cap_file.exists():
        data = json.loads(cap_file.read_text(encoding='utf-8'))['results']
        caps = [r['tbf_cap_mbps'] for r in data]
        tcp_measured = [r['measured_tcp_mbps'] for r in data]

        ax3.plot(caps, caps, 'k--', label='Ideal 100% Link Cap', alpha=0.6)
        ax3.plot(caps, tcp_measured, 'm-^', label='Measured TCP Throughput', linewidth=2)
        ax3.set_title('TBF Bandwidth Cap vs Achieved TCP Throughput')
        ax3.set_xlabel('TBF Shaped Ceiling (Mbps)')
        ax3.set_ylabel('Achieved Throughput (Mbps)')
        ax3.grid(True, alpha=0.3)
        ax3.legend()
    else:
        ax3.text(0.5, 0.5, 'Run: run_link_sweep.py --scenario bandwidth_cap', ha='center')

    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def main():
    p = argparse.ArgumentParser(description='Plot link characterization curves (M/M/1, Mathis, TBF Cap)')
    p.add_argument('--input-dir', default='data/link_sweeps', help='Directory with link sweep JSON files')
    p.add_argument('--output', default='data/link_characterization_curves.png', help='Output PNG file path')
    a = p.parse_args()

    plot_all_link_sweeps(a.input_dir, a.output)
    print(f"Link characterization curves saved to {a.output}")


if __name__ == '__main__':
    main()
