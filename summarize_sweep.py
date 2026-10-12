import argparse
import csv
import json
from pathlib import Path
from common import atomic_json, mean


def aggregate_sweep(run_folders):
    rows = []
    for folder in run_folders:
        folder = Path(folder)
        manifest_path = folder / 'manifest.json'
        summary_path = folder / 'summary.json'
        if not manifest_path.exists() or not summary_path.exists():
            continue

        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        summary = json.loads(summary_path.read_text(encoding='utf-8'))

        # Snapshots data if present
        mean_backlog, mean_rtt, mean_proc = None, None, None
        snap_path = folder / 'snapshots.csv'
        if snap_path.exists():
            snaps = list(csv.DictReader(snap_path.open(encoding='utf-8')))
            active_snaps = [s for s in snaps if str(s.get('active')).lower() in ('true', '1')]
            if active_snaps:
                b_list = [float(s['backlog']) for s in active_snaps if s.get('backlog') not in (None, '')]
                r_list = [float(s['rtt_ms']) for s in active_snaps if s.get('rtt_ms') not in (None, '')]
                p_list = [float(s['processing_ms']) for s in active_snaps if s.get('processing_ms') not in (None, '')]
                mean_backlog = mean(b_list)
                mean_rtt = mean(r_list)
                mean_proc = mean(p_list)

        offered = float(manifest.get('rate', summary.get('offered_rate_in_publish_window', 0.0)))
        steady = summary.get('steady_state', {})
        little = summary.get('littles_law', {})

        rows.append({
            'run_id': manifest.get('run_id'),
            'offered_rate': offered,
            'completed_rate': summary.get('completed_rate_in_publish_window', 0.0),
            'steady_offered_rate': steady.get('offered_rate'),
            'steady_completed_rate': steady.get('completed_rate'),
            'p50_ms_completed': summary.get('p50_ms_completed_cohort'),
            'p95_ms_completed': summary.get('p95_ms_completed_cohort'),
            'p95_ms_with_penalty': summary.get('p95_ms_with_timeout_penalty'),
            'p99_ms_with_penalty': summary.get('p99_ms_with_timeout_penalty'),
            'p95_ms_steady': steady.get('p95_ms'),
            'unfinished_count': summary.get('unfinished_count', len(summary.get('confirmed_unfinished_ids', []))),
            'unfinished_ratio': summary.get('unfinished_ratio', 0.0),
            'survivorship_bias': summary.get('survivorship_bias_detected', False),
            'mean_backlog': mean_backlog,
            'mean_rtt_ms': mean_rtt,
            'mean_processing_ms': mean_proc,
            'little_lambda': little.get('lambda_completed_rate'),
            'little_w_sec': little.get('w_mean_latency_seconds'),
            'little_l_predicted': little.get('l_predicted_items'),
            'little_l_observed': little.get('l_observed_items'),
            'little_rel_error': little.get('relative_error'),
            'little_status': little.get('status')
        })

    rows.sort(key=lambda r: r['offered_rate'])

    # Detect empirical saturation knee point
    knee_point_rate = None
    for r in rows:
        if r['offered_rate'] > 0:
            delivery_ratio = r['completed_rate'] / r['offered_rate']
            if delivery_ratio < 0.90 or r['unfinished_ratio'] > 0.05:
                knee_point_rate = r['offered_rate']
                break

    return {
        'runs_count': len(rows),
        'saturation_knee_point_offered_rate': knee_point_rate,
        'load_points': rows
    }


def main():
    p = argparse.ArgumentParser(description='Aggregate multiple load sweep runs into load curves dataset')
    p.add_argument('--run-ids', nargs='*', help='Explicit list of run IDs')
    p.add_argument('--pattern', default='sweep_*', help='Pattern of folders under data/runs (default: sweep_*)')
    p.add_argument('--output', default='data/sweep_summary.json', help='Output JSON path')
    p.add_argument('--output-csv', default='data/sweep_summary.csv', help='Output CSV path')
    a = p.parse_args()

    runs_base = Path('data/runs')
    if a.run_ids:
        folders = [runs_base / r for r in a.run_ids]
    else:
        folders = sorted(runs_base.glob(a.pattern))

    if not folders:
        p.error(f'No matching run folders found under {runs_base} matching pattern {a.pattern}')

    result = aggregate_sweep(folders)
    atomic_json(Path(a.output), result)

    # Also write CSV table
    if result['load_points']:
        csv_path = Path(a.output_csv)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = list(result['load_points'][0].keys())
        with csv_path.open('w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in result['load_points']:
                writer.writerow(row)

    print(f'Aggregated {len(result["load_points"])} load points into {a.output} and {a.output_csv}')
    print('\n--- LOAD SWEEP SUMMARY TABLE ---')
    print(f'{"Offered":<9} | {"Throughput":<11} | {"p95 (surv)":<11} | {"p95 (penalized)":<15} | {"Unfinished %":<13} | {"Backlog":<8} | {"L (pred vs obs)"}')
    print('-' * 95)
    for r in result['load_points']:
        p95_surv = f"{r['p95_ms_completed']:.1f}ms" if r['p95_ms_completed'] else "N/A"
        p95_pen = f"{r['p95_ms_with_penalty']:.1f}ms" if r['p95_ms_with_penalty'] else "N/A"
        unf_pct = f"{r['unfinished_ratio']*100:.1f}%"
        backlog_str = f"{r['mean_backlog']:.1f}" if r['mean_backlog'] is not None else "N/A"
        l_str = f"{r['little_l_predicted']:.2f} vs {r['little_l_observed']:.2f}" if (r['little_l_predicted'] is not None and r['little_l_observed'] is not None) else "N/A"
        print(f"{r['offered_rate']:<9.1f} | {r['completed_rate']:<11.1f} | {p95_surv:<11} | {p95_pen:<15} | {unf_pct:<13} | {backlog_str:<8} | {l_str}")
    if result['saturation_knee_point_offered_rate']:
        print(f"\nEmpirical Saturation Knee Point detected around offered rate: {result['saturation_knee_point_offered_rate']} msg/s")


if __name__ == '__main__':
    main()
