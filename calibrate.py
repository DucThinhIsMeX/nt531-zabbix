import argparse
import csv
import json
import math
from pathlib import Path
from common import atomic_json, mean, stddev, utc


def compute_calibrated_thresholds(snapshots, baseline_run_id, k=3.0, min_margins=None):
    if min_margins is None:
        min_margins = {'rtt_ms': 5.0, 'processing_ms': 10.0, 'p95_ms': 20.0, 'backlog': 5}

    valid = [s for s in snapshots if str(s.get('active')).lower() in ('true', '1')
             and str(s.get('broker_valid')).lower() in ('true', '1')
             and str(s.get('app_valid')).lower() in ('true', '1')
             and str(s.get('probe_valid')).lower() in ('true', '1')]

    if not valid:
        # Fallback to any active snapshots if probe telemetry was slightly delayed during startup
        valid = [s for s in snapshots if str(s.get('active')).lower() in ('true', '1')]

    if not valid:
        raise ValueError('No active snapshots found in baseline run to calibrate from.')

    series = {
        'rtt_ms': [float(s['rtt_ms']) for s in valid if s.get('rtt_ms') not in (None, '')],
        'processing_ms': [float(s['processing_ms']) for s in valid if s.get('processing_ms') not in (None, '')],
        'p95_ms': [float(s['p95_ms']) for s in valid if s.get('p95_ms') not in (None, '')],
        'backlog': [float(s['backlog']) for s in valid if s.get('backlog') not in (None, '')]
    }

    stats = {}
    for key, values in series.items():
        if not values:
            raise ValueError(f'Metric {key} has no valid numeric entries in baseline snapshots.')
        m = mean(values)
        s = stddev(values) or 0.0
        margin = min_margins.get(key, 5.0)
        t = max(m + k * s, m + margin)
        stats[key] = {'mean': round(m, 2), 'stddev': round(s, 2), 'threshold': round(t, 2), 'n': len(values)}

    return {
        'backlog_max': int(math.ceil(stats['backlog']['threshold'])),
        'p95_max_ms': stats['p95_ms']['threshold'],
        'rtt_max_ms': stats['rtt_ms']['threshold'],
        'processing_max_ms': stats['processing_ms']['threshold'],
        'calibration_metadata': {
          'baseline_run_id': baseline_run_id,
          'calibrated_utc': utc(),
          'k_sigma': k,
          'sample_size': len(valid),
          'statistics': stats,
          'formula': 'threshold = max(mean + min_margin, mean + k * stddev)'
        }
    }


def main():
    p = argparse.ArgumentParser(description='Calibrate thresholds from a baseline pilot run (mean + k*sigma)')
    p.add_argument('--baseline-run-id', required=True, help='Run ID of normal baseline pilot experiment')
    p.add_argument('--k', type=float, default=3.0, help='Sigma multiplier (default: 3.0 for three-sigma rule)')
    p.add_argument('--output', default='thresholds.json', help='Output thresholds JSON path (default: thresholds.json)')
    a = p.parse_args()

    snap_file = Path('data/runs') / a.baseline_run_id / 'snapshots.csv'
    if not snap_file.exists():
        p.error(f'Baseline snapshots not found: {snap_file}. Run baseline experiment first.')

    snapshots = list(csv.DictReader(snap_file.open(encoding='utf-8')))
    thresholds = compute_calibrated_thresholds(snapshots, a.baseline_run_id, k=a.k)
    atomic_json(Path(a.output), thresholds)

    print(f'Calibrated {a.output} from baseline {a.baseline_run_id} (k={a.k}):')
    print(json.dumps(thresholds, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
