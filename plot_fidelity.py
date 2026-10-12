import argparse
import csv
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec


def plot_zabbix_fidelity(report_file, timeseries_file, output_path):
    report_p = Path(report_file)
    ts_p = Path(timeseries_file)

    if not report_p.exists() or not ts_p.exists():
        raise FileNotFoundError(f"Missing input files: {report_p} or {ts_p}")

    report = json.loads(report_p.read_text(encoding='utf-8'))
    
    # Read ground truth
    ts_rows = list(csv.DictReader(ts_p.open(encoding='utf-8')))
    t_vals = [float(r['time_sec']) for r in ts_rows]
    rtt_vals = [float(r['rtt_ms']) for r in ts_rows]

    fig = plt.figure(figsize=(16, 9.5))
    gs = gridspec.GridSpec(2, 2, height_ratios=[1.7, 1.0], hspace=0.32, wspace=0.25)

    ax1 = fig.add_subplot(gs[0, :])
    ax2 = fig.add_subplot(gs[1, 0])
    ax3 = fig.add_subplot(gs[1, 1])

    # 1. Top Panel: Time Series Tracking & Nyquist Blind Spots
    ax1.plot(t_vals, rtt_vals, color='#4A90E2', linewidth=1.5, alpha=0.85, label='Ground Truth (1s High-Freq Ping)')
    ax1.fill_between(t_vals, rtt_vals, color='#4A90E2', alpha=0.12)

    # 30s polling
    p30 = report['polling_intervals'].get('30s', {})
    if 'samples' in p30:
        p30_t = [s['poll_time_sec'] for s in p30['samples']]
        p30_v = [s['sampled_rtt_ms'] for s in p30['samples']]
        ax1.plot(p30_t, p30_v, color='#F39C12', marker='s', markersize=6, linewidth=2.0, linestyle='--', label='Zabbix Agent 30s Polling')

    # 60s polling
    p60 = report['polling_intervals'].get('60s', {})
    if 'samples' in p60:
        p60_t = [s['poll_time_sec'] for s in p60['samples']]
        p60_v = [s['sampled_rtt_ms'] for s in p60['samples']]
        ax1.plot(p60_t, p60_v, color='#E74C3C', marker='D', markersize=7, linewidth=2.2, linestyle='-.', label='Zabbix Default 60s Polling')

    # Threshold line
    thresh = report.get('alarm_threshold_ms', 30.0)
    ax1.axhline(y=thresh, color='#8E44AD', linestyle=':', linewidth=1.8, label=f'Alarm Threshold ({thresh} ms)')

    # Shaded microburst zones
    ax1.axvspan(45, 53, color='#FADBD8', alpha=0.5, label='Micro-burst 1 (8s duration)')
    ax1.axvspan(110, 122, color='#FCF3CF', alpha=0.5, label='Micro-burst 2 (12s duration)')
    ax1.axvspan(180, 240, color='#D4EFDF', alpha=0.35, label='Sustained Congestion (60s)')

    # Annotations
    ax1.annotate('8s Micro-burst: Completely MISSED by 60s polling!', xy=(49, 110), xytext=(55, 125),
                 arrowprops=dict(facecolor='black', shrink=0.08, width=1, headwidth=6),
                 fontsize=9.5, fontweight='bold', bbox=dict(boxstyle="round,pad=0.3", fc="#FDEDEC", ec="#E74C3C"))

    lag60 = p60.get('sustained_fault_detection_lag_sec', 0)
    ax1.annotate(f'Sustained Fault Detection Lag: +{lag60}s delay', xy=(180 + lag60, 85), xytext=(195, 45),
                 arrowprops=dict(facecolor='#E74C3C', shrink=0.08, width=1, headwidth=6),
                 fontsize=9.5, fontweight='bold', bbox=dict(boxstyle="round,pad=0.3", fc="#FEF9E7", ec="#F39C12"))

    ax1.set_title('Zabbix Monitoring Fidelity Evaluation: Polling Interval vs 1-Second Ground Truth Dynamics', fontsize=13, fontweight='bold')
    ax1.set_xlabel('Time elapsed (seconds)', fontweight='bold')
    ax1.set_ylabel('Measured RTT (ms)', fontweight='bold')
    ax1.set_xlim(0, max(t_vals))
    ax1.grid(True, linestyle='--', alpha=0.4)
    ax1.legend(loc='upper right', framealpha=0.9, fontsize=9)

    # 2. Bottom Left Panel: Peak Underestimation
    labels = ['Ground Truth (1s)', 'Zabbix (30s poll)', 'Zabbix (60s poll)']
    peaks = [
        report['ground_truth_peak_ms'],
        p30.get('observed_peak_ms', 0),
        p60.get('observed_peak_ms', 0)
    ]
    errs = [0.0, p30.get('peak_underestimation_pct', 0), p60.get('peak_underestimation_pct', 0)]
    colors = ['#4A90E2', '#F39C12', '#E74C3C']

    bars = ax2.bar(labels, peaks, color=colors, width=0.55, edgecolor='black', linewidth=1.1)
    ax2.set_title('Peak RTT Underestimation by Polling Interval', fontsize=11, fontweight='bold')
    ax2.set_ylabel('Observed Peak Latency (ms)', fontweight='bold')
    ax2.grid(axis='y', linestyle='--', alpha=0.4)

    for bar, peak, err in zip(bars, peaks, errs):
        y_val = bar.get_height()
        err_text = "Baseline (100%)" if err == 0 else f"-{err}% Error"
        ax2.text(bar.get_x() + bar.get_width()/2.0, y_val + 2, f"{peak:.1f} ms\n({err_text})",
                 ha='center', va='bottom', fontsize=9, fontweight='bold')
    ax2.set_ylim(0, max(peaks) * 1.25)

    # 3. Bottom Right Panel: Detection Delay & Shannon-Nyquist Resolution
    metrics = ['Detection Lag (s)', 'Nyquist Min Event (s)']
    v_30 = [p30.get('sustained_fault_detection_lag_sec', 0), p30.get('shannon_nyquist_min_resolvable_burst_sec', 60)]
    v_60 = [p60.get('sustained_fault_detection_lag_sec', 0), p60.get('shannon_nyquist_min_resolvable_burst_sec', 120)]

    x = range(len(metrics))
    w = 0.35
    ax3.bar([i - w/2 for i in x], v_30, width=w, label='30s Polling', color='#F39C12', edgecolor='black')
    ax3.bar([i + w/2 for i in x], v_60, width=w, label='60s Polling', color='#E74C3C', edgecolor='black')

    ax3.set_xticks(list(x))
    ax3.set_xticklabels(metrics, fontweight='bold')
    ax3.set_title('Alert Detection Lag & Nyquist Event Resolution Limit', fontsize=11, fontweight='bold')
    ax3.set_ylabel('Duration / Latency (seconds)', fontweight='bold')
    ax3.grid(axis='y', linestyle='--', alpha=0.4)
    ax3.legend(loc='upper left', framealpha=0.9)

    for i in x:
        ax3.text(i - w/2, v_30[i] + 1.5, f"{v_30[i]}s", ha='center', va='bottom', fontweight='bold', fontsize=9)
        ax3.text(i + w/2, v_60[i] + 1.5, f"{v_60[i]}s", ha='center', va='bottom', fontweight='bold', fontsize=9)
    ax3.set_ylim(0, max(v_60) * 1.22)

    fig.savefig(output_path, dpi=180, bbox_inches='tight')
    plt.close(fig)


def main():
    p = argparse.ArgumentParser(description='Plot Zabbix Fidelity Analysis: Polling intervals vs Ground Truth')
    p.add_argument('--report-json', default='data/zabbix_fidelity/zabbix_fidelity_report.json', help='Fidelity report JSON')
    p.add_argument('--timeseries-csv', default='data/zabbix_fidelity/ground_truth_timeseries_1s.csv', help='Timeseries CSV')
    p.add_argument('--output', default='data/zabbix_fidelity/zabbix_fidelity_analysis.png', help='Output PNG file path')
    a = p.parse_args()

    plot_zabbix_fidelity(a.report_json, a.timeseries_csv, a.output)
    print(f"Zabbix fidelity plot saved to {a.output}")


if __name__ == '__main__':
    main()
