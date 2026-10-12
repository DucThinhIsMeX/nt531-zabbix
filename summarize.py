import argparse
import csv
import json
from pathlib import Path
from common import atomic_json, mean, percentile, read_events


def summarize(events, manifest, snapshots=None):
    attempted = {e['message_id'] for e in events if e['event'] == 'attempted'}
    confirmed = {e['message_id'] for e in events if e['event'] == 'confirmed'}
    completed = {}
    for e in events:
        if e['event'] == 'completed':
            completed.setdefault(e['message_id'], e)

    start, duration = manifest['start_ts'], manifest['duration']
    drain_sec = manifest.get('drain_seconds', 60.0)

    # 1. Publish window completions & latencies
    in_window = [e for e in completed.values() if start <= e['ts'] < start + duration]
    in_window_latencies = [e['latency_ms'] for e in in_window]

    # 2. Entire cohort (including drain) latencies
    cohort_latencies = [e['latency_ms'] for e in completed.values()]

    # 3. Steady-state window (discarding warmup and cooldown to eliminate edge effects)
    warmup = min(15.0, max(5.0, duration * 0.1)) if duration >= 20 else 0.0
    cooldown = min(15.0, max(5.0, duration * 0.1)) if duration >= 20 else 0.0
    steady_start = start + warmup
    steady_end = start + duration - cooldown
    steady_dur = max(0.001, steady_end - steady_start)

    steady_completions = [e for e in completed.values() if steady_start <= e['ts'] < steady_end]
    steady_latencies = [e['latency_ms'] for e in steady_completions]
    steady_attempted = [e for e in events if e['event'] == 'attempted' and steady_start <= e['ts'] < steady_end]

    # 4. Survivorship Bias Handling
    unfinished_ids = sorted(confirmed - set(completed))
    unfinished_count = len(unfinished_ids)
    unfinished_ratio = (unfinished_count / len(confirmed)) if confirmed else 0.0

    # For conservative percentile estimation, penalize unfinished messages with ceiling timeout
    timeout_ceiling_ms = (duration + drain_sec) * 1000.0
    penalized_latencies = cohort_latencies + [timeout_ceiling_ms] * unfinished_count

    # 5. Little's Law Analysis: L = lambda * W
    lambda_completed = len(in_window) / duration
    mean_latency_sec = (mean(in_window_latencies) / 1000.0) if in_window_latencies else (
        (mean(cohort_latencies) / 1000.0) if cohort_latencies else 0.0
    )
    l_predicted = lambda_completed * mean_latency_sec

    l_observed = None
    l_rel_error = None
    littles_law_status = 'no_snapshot_data'
    if snapshots:
        active_snaps = [s for s in snapshots if str(s.get('active')).lower() in ('true', '1')]
        if active_snaps:
            backlog_vals = [float(s['backlog']) for s in active_snaps if s.get('backlog') not in (None, '')]
            proc_vals = [float(s['processing_ms']) for s in active_snaps if s.get('processing_ms') not in (None, '')]
            mean_backlog = mean(backlog_vals) if backlog_vals else 0.0
            mean_proc_sec = (mean(proc_vals) / 1000.0) if proc_vals else 0.02
            # Total items in system = backlog in queue + in-flight processing items
            in_flight = lambda_completed * mean_proc_sec
            l_observed = mean_backlog + in_flight
            if l_observed > 0:
                l_rel_error = abs(l_predicted - l_observed) / l_observed
                littles_law_status = 'verified_stationary' if l_rel_error <= 0.25 else 'diverges_queue_growing'
            else:
                l_rel_error = 0.0
                littles_law_status = 'idle_or_empty'

    return {
        'run_id': manifest['run_id'],
        'status': manifest.get('status'),
        'attempted': len(attempted),
        'confirmed': len(confirmed),
        'completed_unique_including_drain': len(completed),
        'offered_rate_in_publish_window': len([e for e in events if e['event'] == 'attempted'
                                             and start <= e['ts'] < start + duration]) / duration,
        'completed_rate_in_publish_window': len(in_window) / duration,

        # Aligned publish window latencies
        'p50_ms_in_publish_window': percentile(in_window_latencies, 50),
        'p95_ms_in_publish_window': percentile(in_window_latencies, 95),
        'p99_ms_in_publish_window': percentile(in_window_latencies, 99),

        # Steady-state window (cleanest load curve measurement)
        'steady_state': {
            'warmup_seconds': warmup,
            'cooldown_seconds': cooldown,
            'steady_duration_seconds': steady_dur,
            'offered_rate': len(steady_attempted) / steady_dur,
            'completed_rate': len(steady_completions) / steady_dur,
            'p50_ms': percentile(steady_latencies, 50),
            'p95_ms': percentile(steady_latencies, 95),
            'p99_ms': percentile(steady_latencies, 99),
            'mean_latency_ms': mean(steady_latencies)
        },

        # Survivorship bias corrected metrics
        'unfinished_count': unfinished_count,
        'unfinished_ratio': unfinished_ratio,
        'survivorship_bias_detected': unfinished_ratio > 0.01,
        'p50_ms_with_timeout_penalty': percentile(penalized_latencies, 50),
        'p95_ms_with_timeout_penalty': percentile(penalized_latencies, 95),
        'p99_ms_with_timeout_penalty': percentile(penalized_latencies, 99),

        # Legacy cohort percentiles (survivors only)
        'p50_ms_completed_cohort': percentile(cohort_latencies, 50),
        'p95_ms_completed_cohort': percentile(cohort_latencies, 95),
        'p99_ms_completed_cohort': percentile(cohort_latencies, 99),

        'confirmed_unfinished_ids': unfinished_ids,
        'completed_without_confirm_ids': sorted(set(completed) - confirmed),
        'duplicates': sum(e['event'] == 'duplicate' for e in events),
        'load_limited_slots': sum(e['event'] == 'load_limited' for e in events),
        'publish_failed_or_unknown': sum(e['event'] == 'publish_failed_or_unknown' for e in events),

        # Little's Law verification
        'littles_law': {
            'lambda_completed_rate': lambda_completed,
            'w_mean_latency_seconds': mean_latency_sec,
            'l_predicted_items': l_predicted,
            'l_observed_items': l_observed,
            'relative_error': l_rel_error,
            'status': littles_law_status,
            'note': 'L = lambda * W valid in stationary state. Divergence indicates non-stationary queue growth under saturation.'
        },

        'note': 'Percentiles report both completed survivors and conservative timeout-penalized figures to eliminate survivorship bias at saturation.'
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--run-id', required=True)
    a = p.parse_args()
    folder = Path('data/runs') / a.run_id
    manifest = json.loads((folder / 'manifest.json').read_text())
    if manifest['status'] == 'running':
        p.error('Wait until producer finishes')

    snapshots = None
    snap_path = folder / 'snapshots.csv'
    if snap_path.exists():
        snapshots = list(csv.DictReader(snap_path.open(encoding='utf-8')))

    result = summarize(read_events(folder / 'events.jsonl'), manifest, snapshots)
    atomic_json(folder / 'summary.json', result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
