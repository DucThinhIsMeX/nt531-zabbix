import argparse
import csv
import json
import math
import random
from pathlib import Path
from common import atomic_json, mean, stddev, utc


def generate_or_load_timeseries(snapshots_file=None, duration=300):
    # If a real snapshots.csv is provided, extract its time series
    if snapshots_file and Path(snapshots_file).exists():
        rows = list(csv.DictReader(Path(snapshots_file).open(encoding='utf-8')))
        if rows:
            start_ts = float(rows[0]['ts'])
            ts_series = []
            for r in rows:
                t = round(float(r['ts']) - start_ts, 1)
                rtt = float(r['rtt_ms']) if r.get('rtt_ms') else 2.0
                ts_series.append({'time_sec': t, 'rtt_ms': rtt})
            return ts_series

    # Otherwise synthesize a realistic 1-second ground truth series:
    # Baseline ~2.5ms RTT, with 2 micro-bursts (durations: 8s and 12s) and 1 sustained fault (60s)
    series = []
    for t in range(duration):
        val = 2.5 + random.gauss(0, 0.3)
        # Micro-burst 1: t in [45..53] (8 seconds, peak 140ms)
        if 45 <= t <= 53:
            val += 135.0 * math.sin((t - 45) / 8.0 * math.pi)
        # Micro-burst 2: t in [110..122] (12 seconds, peak 110ms)
        elif 110 <= t <= 122:
            val += 105.0 * math.sin((t - 110) / 12.0 * math.pi)
        # Sustained congestion: t in [180..240] (60 seconds, peak 90ms)
        elif 180 <= t <= 240:
            val += 85.0 + random.gauss(0, 3.0)
        series.append({'time_sec': float(t), 'rtt_ms': max(1.0, round(val, 2))})
    return series


def evaluate_zabbix_polling_fidelity(ts_series, poll_intervals=(30, 60), alarm_threshold=30.0):
    t_max = int(ts_series[-1]['time_sec'])
    val_map = {int(r['time_sec']): r['rtt_ms'] for r in ts_series}

    true_peak = max(r['rtt_ms'] for r in ts_series)
    true_mean = mean([r['rtt_ms'] for r in ts_series])

    results = {
        'evaluation_at_utc': utc(),
        'ground_truth_samples_1s': len(ts_series),
        'ground_truth_peak_ms': true_peak,
        'ground_truth_mean_ms': round(true_mean, 2),
        'alarm_threshold_ms': alarm_threshold,
        'polling_intervals': {}
    }

    # Evaluate each polling interval
    for interval in poll_intervals:
        poll_samples = []
        poll_times = list(range(0, t_max + 1, interval))

        for pt in poll_times:
            # Zabbix poll snapshot takes instantaneous sample at poll time
            sampled_val = val_map.get(pt, val_map.get(pt - 1, 2.5))
            poll_samples.append({'poll_time_sec': pt, 'sampled_rtt_ms': sampled_val})

        sampled_vals = [s['sampled_rtt_ms'] for s in poll_samples]
        poll_peak = max(sampled_vals)
        peak_err_pct = round(((true_peak - poll_peak) / true_peak) * 100.0, 1)

        # Micro-burst detection analysis:
        # Micro-burst 1 occurred at t=45..53
        mb1_max_truth = max(val_map[t] for t in range(45, 54))
        mb1_detected = any(s['sampled_rtt_ms'] >= alarm_threshold for s in poll_samples if 40 <= s['poll_time_sec'] <= 65)

        # Micro-burst 2 occurred at t=110..122
        mb2_max_truth = max(val_map[t] for t in range(110, 123))
        mb2_detected = any(s['sampled_rtt_ms'] >= alarm_threshold for s in poll_samples if 105 <= s['poll_time_sec'] <= 135)

        # Detection lag for sustained fault (starts at t=180)
        first_poll_alarm = next((s['poll_time_sec'] for s in poll_samples if s['poll_time_sec'] >= 180 and s['sampled_rtt_ms'] >= alarm_threshold), None)
        detection_lag_sec = (first_poll_alarm - 180) if first_poll_alarm is not None else None

        results['polling_intervals'][f'{interval}s'] = {
            'poll_interval_sec': interval,
            'samples_count': len(poll_samples),
            'observed_peak_ms': poll_peak,
            'peak_underestimation_pct': peak_err_pct,
            'microburst_8s_detected': mb1_detected,
            'microburst_12s_detected': mb2_detected,
            'sustained_fault_detection_lag_sec': detection_lag_sec,
            'shannon_nyquist_min_resolvable_burst_sec': interval * 2,
            'samples': poll_samples
        }

    return results


def main():
    p = argparse.ArgumentParser(description='Evaluate Zabbix Monitoring Fidelity vs 1-second Ground Truth')
    p.add_argument('--snapshots', help='Optional path to actual snapshots.csv')
    p.add_argument('--output-dir', default='data/zabbix_fidelity', help='Output directory')
    a = p.parse_args()

    out_dir = Path(a.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    series = generate_or_load_timeseries(a.snapshots, duration=300)
    fidelity = evaluate_zabbix_polling_fidelity(series, poll_intervals=[30, 60], alarm_threshold=30.0)

    # Save full ground truth and fidelity report
    truth_path = out_dir / 'ground_truth_timeseries_1s.csv'
    with truth_path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['time_sec', 'rtt_ms'])
        writer.writeheader()
        for r in series:
            writer.writerow(r)

    report_path = out_dir / 'zabbix_fidelity_report.json'
    atomic_json(report_path, fidelity)

    print("\n=== ZABBIX MONITORING FIDELITY EVALUATION ===")
    print(f"Ground Truth Peak RTT: {fidelity['ground_truth_peak_ms']} ms | Mean: {fidelity['ground_truth_mean_ms']} ms")
    print("-" * 80)
    for name, stats in fidelity['polling_intervals'].items():
        print(f"Polling Interval: {name}")
        print(f"  Observed Peak:        {stats['observed_peak_ms']} ms (Peak Underestimation: {stats['peak_underestimation_pct']}%)")
        print(f"  8s Micro-burst:       {'DETECTED' if stats['microburst_8s_detected'] else 'MISSED (Completely Blind)'}")
        print(f"  12s Micro-burst:      {'DETECTED' if stats['microburst_12s_detected'] else 'MISSED (Completely Blind)'}")
        print(f"  Sustained Fault Lag:  {stats['sustained_fault_detection_lag_sec']} seconds")
        print(f"  Nyquist Min Event:    {stats['shannon_nyquist_min_resolvable_burst_sec']} seconds")
        print()
    print(f"Saved fidelity report to {report_path} and {truth_path}")


if __name__ == '__main__':
    main()
