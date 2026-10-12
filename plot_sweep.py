import argparse
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def plot_load_curves(sweep_data, output_path):
    points = sweep_data.get('load_points', [])
    if not points:
        raise ValueError('No load points available to plot.')

    x = [p['offered_rate'] for p in points]
    throughput = [p['completed_rate'] for p in points]
    p50 = [p['p50_ms_completed'] if p['p50_ms_completed'] is not None else float('nan') for p in points]
    p95_surv = [p['p95_ms_completed'] if p['p95_ms_completed'] is not None else float('nan') for p in points]
    p95_pen = [p['p95_ms_with_penalty'] if p['p95_ms_with_penalty'] is not None else float('nan') for p in points]
    unfinished_pct = [p['unfinished_ratio'] * 100 for p in points]
    knee = sweep_data.get('saturation_knee_point_offered_rate')
    prod_ceil = sweep_data.get('producer_ceiling_rate')

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    ((ax1, ax2), (ax3, ax4)) = axes

    # 1. Throughput Curve
    ax1.plot(x, x, 'k--', alpha=0.5, label='Ideal capacity (y = x)')
    ax1.plot(x, throughput, 'b-o', linewidth=2, label='Measured Throughput')

    prod_limited_x = [p['offered_rate'] for p in points if p.get('producer_limited')]
    prod_limited_y = [p['completed_rate'] for p in points if p.get('producer_limited')]
    if prod_limited_x:
        ax1.scatter(prod_limited_x, prod_limited_y, color='darkorange', marker='^', s=120, zorder=5,
                    label='Producer-limited (Sync confirm lock)')
    if knee:
        ax1.axvline(knee, color='red', linestyle=':', label=f'Consumer saturation (~{knee:.1f} msg/s)')
    if prod_ceil and (not knee or abs(prod_ceil - knee) > 2):
        ax1.axvline(prod_ceil, color='darkorange', linestyle='--', label=f'Producer confirm limit (~{prod_ceil:.1f} msg/s)')
    ax1.set_title('Offered Load vs Throughput (Completed Rate)')
    ax1.set_xlabel('Measured Offered Load (msg/s)')
    ax1.set_ylabel('Completed Rate (msg/s)')
    ax1.grid(True, alpha=0.3)
    ax1.legend()

    # 2. Latency Curve (Hockey-Stick Curve & Survivorship Bias)
    ax2.plot(x, p50, 'g-^', label='p50 Latency')
    ax2.plot(x, p95_surv, 'b-s', label='p95 (Survivors only - Deceptive)')
    ax2.plot(x, p95_pen, 'r-o', linewidth=2, label='p95 (With Timeout Penalty - Corrected)')
    if knee:
        ax2.axvline(knee, color='red', linestyle=':', alpha=0.7)
    ax2.set_title('Offered Load vs Latency (Hockey-Stick Curve)')
    ax2.set_xlabel('Measured Offered Load (msg/s)')
    ax2.set_ylabel('Latency (ms)')
    ax2.grid(True, alpha=0.3)
    ax2.legend()

    # 3. Unfinished Ratio Curve
    ax3.plot(x, unfinished_pct, 'm-d', linewidth=2, label='Unfinished Ratio (%)')
    if knee:
        ax3.axvline(knee, color='red', linestyle=':', alpha=0.7)
    ax3.set_title('Offered Load vs Unfinished / Timeout Messages (%)')
    ax3.set_xlabel('Measured Offered Load (msg/s)')
    ax3.set_ylabel('Unfinished Ratio (%)')
    ax3.grid(True, alpha=0.3)
    ax3.legend()

    # 4. Little's Law Verification (L = lambda * W)
    l_pred = [p['little_l_predicted'] if p.get('little_l_predicted') is not None else float('nan') for p in points]
    l_obs = [p['little_l_observed'] if p.get('little_l_observed') is not None else float('nan') for p in points]
    has_little = any(p.get('little_l_observed') is not None for p in points)
    if has_little:
        ax4.plot(x, l_pred, 'c-o', label=r'Predicted $L = \lambda \cdot W$')
        ax4.plot(x, l_obs, 'k--s', label=r'Observed $L$ (Backlog + in-flight)')
        ax4.set_title(r"Little's Law Empirical Check ($L = \lambda W$)")
        ax4.set_xlabel('Offered Load (msg/s)')
        ax4.set_ylabel('Average Items in System (L)')
        ax4.grid(True, alpha=0.3)
        ax4.legend()
    else:
        # If no snapshots, plot mean backlog or queue slots
        backlogs = [p['mean_backlog'] if p.get('mean_backlog') is not None else float('nan') for p in points]
        ax4.plot(x, backlogs, 'orange', marker='o', label='Mean Backlog')
        ax4.set_title('Offered Load vs Mean Backlog')
        ax4.set_xlabel('Offered Load (msg/s)')
        ax4.set_ylabel('Backlog items')
        ax4.grid(True, alpha=0.3)
        ax4.legend()

    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def main():
    p = argparse.ArgumentParser(description='Plot load-performance curves from load sweep aggregation')
    p.add_argument('--sweep-json', default='data/sweep_summary.json', help='Input sweep JSON')
    p.add_argument('--output', default='data/load_curves.png', help='Output PNG file path')
    a = p.parse_args()

    data_file = Path(a.sweep_json)
    if not data_file.exists():
        p.error(f'Sweep summary file {data_file} not found. Run summarize_sweep.py first.')

    sweep_data = json.loads(data_file.read_text(encoding='utf-8'))
    plot_load_curves(sweep_data, a.output)
    print(f'Load-performance curves saved to {a.output}')


if __name__ == '__main__':
    main()
