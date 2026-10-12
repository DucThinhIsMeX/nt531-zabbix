import argparse
import json
from pathlib import Path
from common import atomic_json, percentile, read_events


def summarize(events, manifest):
    attempted = {e['message_id'] for e in events if e['event']=='attempted'}
    confirmed = {e['message_id'] for e in events if e['event']=='confirmed'}
    completed = {}
    for e in events:
        if e['event']=='completed':
            completed.setdefault(e['message_id'], e)
    start, duration = manifest['start_ts'], manifest['duration']
    in_window = [e for e in completed.values() if start <= e['ts'] < start+duration]
    latencies = [e['latency_ms'] for e in completed.values()]
    return {'run_id': manifest['run_id'], 'status': manifest.get('status'),
            'attempted': len(attempted), 'confirmed': len(confirmed),
            'completed_unique_including_drain': len(completed),
            'offered_rate_in_publish_window': len([e for e in events if e['event']=='attempted'
                                                 and start <= e['ts'] < start+duration])/duration,
            'completed_rate_in_publish_window': len(in_window)/duration,
            'p50_ms_completed_cohort': percentile(latencies, 50),
            'p95_ms_completed_cohort': percentile(latencies, 95),
            'p99_ms_completed_cohort': percentile(latencies, 99),
            'confirmed_unfinished_ids': sorted(confirmed-set(completed)),
            'completed_without_confirm_ids': sorted(set(completed)-confirmed),
            'duplicates': sum(e['event']=='duplicate' for e in events),
            'load_limited_slots': sum(e['event']=='load_limited' for e in events),
            'publish_failed_or_unknown': sum(e['event']=='publish_failed_or_unknown' for e in events),
            'note': 'Percentiles cover completed messages only. Unfinished IDs are reported separately; timeout is not proven permanent loss.'}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--run-id', required=True)
    a = p.parse_args()
    folder = Path('data/runs')/a.run_id
    manifest = json.loads((folder/'manifest.json').read_text())
    if manifest['status']=='running':
        p.error('Wait until producer finishes')
    result = summarize(read_events(folder/'events.jsonl'), manifest)
    atomic_json(folder/'summary.json', result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
