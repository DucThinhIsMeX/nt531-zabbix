import argparse
import csv
import json
import os
import subprocess
import time
from pathlib import Path
from urllib.parse import quote
import requests
from common import load_env, percentile, read_events, utc
from diagnose import CODES, StableLabel, diagnose


def push(s, label):
    host = os.getenv('ZABBIX_APP_HOST', 'Lab-App')
    values = {'app.metrics.valid': int(s['broker_valid'] and s['app_valid']),
              'app.diagnosis.code': CODES[label], 'app.completed_rate': s['completed_rate'],
              'app.queue.alarm': s.get('queue_alarm', 0)}
    if s.get('offered_rate') is not None:
        values['app.offered_rate'] = s['offered_rate']
    if s.get('unfinished_count') is not None:
        values['app.unfinished_count'] = s['unfinished_count']
    if s.get('backlog') is not None:
        values['app.backlog'] = s['backlog']
    if s.get('rtt_ms') is not None:
        values['app.rtt_ms'] = s['rtt_ms']
    if s.get('p95_ms') is not None:
        values['app.latency.p95'] = s['p95_ms']
    if s.get('processing_ms') is not None:
        values['app.processing.mean'] = s['processing_ms']

    # Batch send via stdin for lower latency, fallback to per-item on failure
    lines = [f"{host} {k} {v}" for k, v in values.items()]
    payload = '\n'.join(lines) + '\n'
    result = subprocess.run(['zabbix_sender', '-z', os.environ['ZABBIX_SERVER'], '-i', '-'],
                            input=payload, capture_output=True, text=True, timeout=8)
    if result.returncode:
        for key, value in values.items():
            r = subprocess.run(['zabbix_sender', '-z', os.environ['ZABBIX_SERVER'],
                                '-s', host, '-k', key, '-o', str(value)],
                               capture_output=True, text=True, timeout=8)
            if r.returncode:
                print('Sender failed:', key, r.stdout, r.stderr, flush=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--run-id', required=True)
    p.add_argument('--interval', type=float, default=10)
    p.add_argument('--push-zabbix', action='store_true')
    a = p.parse_args()
    if a.interval < 5:
        p.error('interval must be >=5 seconds')
    load_env()
    folder = Path('data/runs')/a.run_id
    if not (folder/'manifest.json').exists():
        p.error('Start producer first: manifest.json must exist')
    thresholds = json.loads(Path('thresholds.json').read_text())
    base = 'http://'+os.environ['RABBIT_HOST']+':'+os.getenv('RABBIT_HTTP_PORT', '15672')
    auth = (os.getenv('RABBIT_MONITOR_USER', os.environ['RABBIT_USER']),
            os.getenv('RABBIT_MONITOR_PASSWORD', os.environ['RABBIT_PASSWORD']))
    queue_url = base+'/api/queues/'+quote(os.getenv('RABBIT_VHOST', 'lab'), safe='')+'/work_queue'
    probe_url = 'http://'+os.environ['CONSUMER_HOST']+':9109/metrics'
    session = requests.Session()
    stable, queue_stable = StableLabel(2), StableLabel(2)
    previous = time.time()-a.interval
    fields = ['utc','ts','active','broker_valid','app_valid','probe_valid','backlog','consumers',
              'rtt_ms','processing_ms','offered_rate','completed_rate','unfinished_count','p95_ms','label','reason','queue_alarm']
    path = folder/'snapshots.csv'
    if path.exists():
        p.error('snapshots.csv exists; do not overwrite. Use a new run-id.')
    print('Collecting. Ctrl+C AFTER run finishes.', flush=True)
    try:
        with path.open('w', newline='', encoding='utf-8') as file:
            writer = csv.DictWriter(file, fieldnames=fields)
            writer.writeheader()
            while True:
                now = time.time()
                try:
                    manifest = json.loads((folder/'manifest.json').read_text())
                    events = read_events(folder/'events.jsonl')
                    recent = [e for e in events if e['event']=='completed' and previous < e['ts'] <= now]
                    recent_attempted = [e for e in events if e['event']=='attempted' and previous < e['ts'] <= now]
                    all_confirmed = sum(1 for e in events if e['event']=='confirmed')
                    all_completed = sum(1 for e in events if e['event']=='completed')
                    unfinished_count = max(0, all_confirmed - all_completed)
                    heartbeat = json.loads((folder/'heartbeat.json').read_text())
                    app_valid = manifest.get('status') != 'running' or -2 <= time.time()-heartbeat['ts'] <= 30
                except (OSError, ValueError, KeyError):
                    manifest, recent, recent_attempted, unfinished_count, app_valid = {}, [], [], 0, False
                s = dict(utc=utc(), ts=now, active=manifest.get('status')=='running',
                         broker_valid=False, app_valid=app_valid, probe_valid=False,
                         backlog=None, consumers=None, rtt_ms=None, processing_ms=None,
                         offered_rate=len(recent_attempted)/max(.001, now-previous),
                         completed_rate=len(recent)/max(.001, now-previous),
                         unfinished_count=unfinished_count,
                         p95_ms=percentile([e['latency_ms'] for e in recent], 95))
                try:
                    r = session.get(queue_url, auth=auth, timeout=3)
                    r.raise_for_status()
                    v = r.json()
                    s.update(broker_valid=True, backlog=v['messages_ready']+v['messages_unacknowledged'],
                             consumers=v['consumers'])
                except (requests.RequestException, ValueError, KeyError, TypeError):
                    pass
                try:
                    r = session.get(probe_url, timeout=3)
                    r.raise_for_status()
                    v = r.json()
                    observed_at = time.time()
                    skew = observed_at - v['ts']
                    if skew < -2 or skew > 15:
                        print(f"WARNING: Telemetry probe clock skew/delay ({skew:.1f}s) exceeded tolerance [-2s..15s]. Run chrony/ntp.", flush=True)
                    fresh = -2 <= skew <= 15
                    services = [w['processing_ms'] for w in v.get('workers', []) if w['run_id']==a.run_id
                                and -2 <= observed_at-w['ts'] <= 30]
                    s.update(probe_valid=fresh and v.get('rtt_ms') is not None,
                             rtt_ms=v.get('rtt_ms') if fresh else None,
                             processing_ms=sum(services)/len(services) if services and fresh else None)
                except (requests.RequestException, ValueError, KeyError, TypeError):
                    pass
                candidate, reason = diagnose(s, thresholds)
                label = stable.update(candidate)
                queue_candidate = 'ALARM' if s['active'] and s['broker_valid'] and s['backlog'] > thresholds['backlog_max'] else 'OK'
                queue_alarm = queue_stable.update(queue_candidate) == 'ALARM'
                s.update(label=label, reason=reason, queue_alarm=int(queue_alarm))
                writer.writerow(s)
                file.flush()
                print(label, reason, 'backlog=',s['backlog'], 'p95=',s['p95_ms'], flush=True)
                if a.push_zabbix:
                    try:
                        push(s, label)
                    except (OSError, subprocess.TimeoutExpired) as error:
                        print('Sender error:', error, flush=True)
                previous = now
                time.sleep(max(0, a.interval-(time.time()-now)))
    except KeyboardInterrupt:
        print('Snapshots saved:', path)


if __name__ == '__main__':
    main()
