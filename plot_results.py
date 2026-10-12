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
fig, axes = plt.subplots(4, 1, figsize=(11, 10), sharex=True)
for ax, keys, title in zip(axes, [('backlog',),('completed_rate',),('p95_ms','processing_ms'),('rtt_ms',)],
                           ['Request backlog', 'Unique completions per second', 'Application and processing latency (ms)', 'C to B ICMP RTT (ms)']):
    for key in keys:
        values = [float(r[key]) if r[key] else float('nan') for r in rows]
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
