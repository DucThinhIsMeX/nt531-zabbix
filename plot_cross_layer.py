import argparse
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def plot_cross_layer_causality(data_file, output_path):
    path = Path(data_file)
    if not path.exists():
        raise FileNotFoundError(f"Cross layer summary file {path} not found.")

    raw = json.loads(path.read_text(encoding='utf-8'))
    loss_data = raw.get('loss_causality_matrix', [])
    util_data = raw.get('utilization_causality_matrix', [])

    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(19, 5.5))

    # 1. Packet Loss Impact: Infra TCP vs Service AMQP Goodput
    losses = [r['netem_loss_pct'] for r in loss_data]
    tcp_mbps = [r['infra_tcp_throughput_mbps'] for r in loss_data]
    app_msgs = [r['service_throughput_msg_s'] for r in loss_data]

    color_tcp = 'tab:green'
    color_app = 'tab:blue'

    ax1.set_title('Cross-Layer Loss: L4 TCP vs L7 AMQP Collapse', fontsize=12, fontweight='bold')
    ax1.set_xlabel('Netem Packet Loss (%)', fontweight='bold')
    ax1.set_ylabel('Infra TCP Throughput (Mbps)', color=color_tcp, fontweight='bold')
    line1 = ax1.plot(losses, tcp_mbps, color=color_tcp, marker='s', linewidth=2, label='L4 TCP Throughput')
    ax1.tick_params(axis='y', labelcolor=color_tcp)
    ax1.grid(True, alpha=0.3)

    ax1_twin = ax1.twinx()
    ax1_twin.set_ylabel('App Goodput (msg/s)', color=color_app, fontweight='bold')
    line2 = ax1_twin.plot(losses, app_msgs, color=color_app, marker='o', linewidth=2, linestyle='--', label='L7 AMQP Msg/s')
    ax1_twin.tick_params(axis='y', labelcolor=color_app)

    # Combined legend
    lines = line1 + line2
    labels = [l.get_label() for l in lines]
    ax1.legend(lines, labels, loc='upper right')

    # 2. Link Utilization vs Queue Backlogs (qdisc vs RabbitMQ)
    rhos = [r['link_utilization_rho'] for r in util_data]
    qdisc_kb = [r['infra_qdisc_backlog_bytes'] / 1024.0 for r in util_data]
    rabbit_msgs = [r['service_backlog_messages'] for r in util_data]

    ax2.set_title('Utilization Bottleneck: qdisc vs RabbitMQ Backlog', fontsize=12, fontweight='bold')
    ax2.set_xlabel('Link Utilization (rho = Throughput / {$LINK.CAP})', fontweight='bold')
    ax2.set_ylabel('Linux qdisc Buffer (KB)', color='tab:purple', fontweight='bold')
    l_qdisc = ax2.plot(rhos, qdisc_kb, color='tab:purple', marker='^', linewidth=2, label='Infra qdisc Backlog')
    ax2.tick_params(axis='y', labelcolor='tab:purple')
    ax2.grid(True, alpha=0.3)

    ax2_twin = ax2.twinx()
    ax2_twin.set_ylabel('RabbitMQ Backlog (Messages)', color='tab:red', fontweight='bold')
    l_rabbit = ax2_twin.plot(rhos, rabbit_msgs, color='tab:red', marker='d', linewidth=2, linestyle='--', label='RabbitMQ Queue Lq')
    ax2_twin.tick_params(axis='y', labelcolor='tab:red')

    lines_util = l_qdisc + l_rabbit
    ax2.legend(lines_util, [l.get_label() for l in lines_util], loc='upper left')

    # 3. Loss vs Application p95 Latency & Unfinished Rate
    unf_pct = [r['service_unfinished_pct'] for r in loss_data]
    p95_ms = [r['service_p95_latency_ms'] for r in loss_data]

    ax3.set_title('Cross-Layer Service Degradation & Drop Rate', fontsize=12, fontweight='bold')
    ax3.set_xlabel('Netem Packet Loss (%)', fontweight='bold')
    ax3.set_ylabel('Application p95 Latency (ms)', color='tab:orange', fontweight='bold')
    l_p95 = ax3.plot(losses, p95_ms, color='tab:orange', marker='o', linewidth=2, label='App p95 Latency')
    ax3.tick_params(axis='y', labelcolor='tab:orange')
    ax3.grid(True, alpha=0.3)

    ax3_twin = ax3.twinx()
    ax3_twin.set_ylabel('Unfinished / Timeout Messages (%)', color='tab:gray', fontweight='bold')
    l_unf = ax3_twin.plot(losses, unf_pct, color='tab:gray', marker='x', linewidth=2, linestyle=':', label='Unfinished Ratio (%)')
    ax3_twin.tick_params(axis='y', labelcolor='tab:gray')

    lines_lat = l_p95 + l_unf
    ax3.legend(lines_lat, [l.get_label() for l in lines_lat], loc='upper left')

    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def main():
    p = argparse.ArgumentParser(description='Plot Cross-Layer Causality: Infrastructure degradation mapped to Service QoS')
    p.add_argument('--summary-json', default='data/cross_layer/cross_layer_summary.json', help='Input cross layer summary JSON')
    p.add_argument('--output', default='data/cross_layer/cross_layer_causality_curves.png', help='Output PNG file path')
    a = p.parse_args()

    plot_cross_layer_causality(a.summary_json, a.output)
    print(f"Cross-layer causality curves saved to {a.output}")


if __name__ == '__main__':
    main()
