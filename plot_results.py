import argparse
import csv
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from common import read_events

p = argparse.ArgumentParser()
p.add_argument('--run-id', required=True)
a = p.parse_args()
folder = Path('data/runs')/a.run_id
rows = list(csv.DictReader((folder/'snapshots.csv').open()))
if not rows:
    p.error('No snapshot rows')
start = float(rows[0]['ts'])
x = [float(r['ts'])-start for r in rows]
keys_list = [
    ('backlog', 'unfinished_count'),
    ('offered_rate', 'completed_rate'),
    ('p95_ms', 'processing_ms'),
    ('rtt_ms',)
]
titles = [
    'Queue Backlog and Unfinished Messages',
    'Throughput vs Offered Rate (msg/s)',
    'Application Latency p95 and Processing Time (ms)',
    'C to B ICMP RTT (ms)'
]
fig, axes = plt.subplots(4, 1, figsize=(11, 10), sharex=True)
for ax, keys, title in zip(axes, keys_list, titles):
    for key in keys:
        values = [float(r[key]) if r.get(key) else float('nan') for r in rows]
        if any(not (v != v) for v in values):  # check if at least one non-nan value exists
            ax.plot(x, values, label=key)
    for fault in read_events(folder/'faults.jsonl'):
        ax.axvline(fault['ts']-start, color='gray', linestyle='--', alpha=.6)
    ax.set_title(title)
    ax.legend()
    ax.grid(alpha=.25)
axes[-1].set_xlabel('Seconds since first snapshot')
fig.tight_layout()
fig.savefig(folder/'timeline.png', dpi=160)
print(folder/'timeline.png')
