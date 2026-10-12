import argparse
from pathlib import Path
from common import log

p = argparse.ArgumentParser(description='Manual ground truth; not read by classifier')
p.add_argument('--run-id', required=True)
p.add_argument('--label', required=True, choices=['NORMAL','NETWORK_DELAY','CONSUMER_SLOW','CONSUMER_DOWN','MIXED','TRANSITION'])
a = p.parse_args()
folder = Path('data/runs')/a.run_id
if not folder.exists():
    p.error('Unknown run')
log(folder/'faults.jsonl', label=a.label)
print('Marked', a.label, 'at current time. Run this on A at the actual applied fault time.')
