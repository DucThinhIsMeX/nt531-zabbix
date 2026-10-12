import argparse
import csv
import json
from pathlib import Path
from common import atomic_json, read_events

EXPECTED = {'NORMAL':'NORMAL', 'NETWORK_DELAY':'NETWORK_SUSPECTED',
            'CONSUMER_SLOW':'CONSUMER_SLOW_SUSPECTED', 'CONSUMER_DOWN':'CONSUMER_DOWN',
            'MIXED':'INCONCLUSIVE'}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--run-id', required=True)
    a = p.parse_args()
    folder = Path('data/runs')/a.run_id
    rows = list(csv.DictReader((folder/'snapshots.csv').open()))
    faults = sorted(read_events(folder/'faults.jsonl'), key=lambda f:f['ts'])
    if not faults:
        p.error('No ground truth. Use mark_fault.py during the experiment.')
    matrix, classified, correct, inconclusive = {}, 0, 0, 0
    normal, false_a, false_b = 0, 0, 0
    detections = []
    for i, fault in enumerate(faults):
        end = faults[i+1]['ts'] if i+1 < len(faults) else float('inf')
        segment = [r for r in rows if fault['ts'] <= float(r['ts']) < end and r['active']=='True']
        if fault['label']=='TRANSITION':
            continue
        expected = EXPECTED[fault['label']]
        for r in segment:
            key = expected+' -> '+r['label']
            matrix[key] = matrix.get(key, 0)+1
            classified += 1
            correct += r['label']==expected
            inconclusive += r['label']=='INCONCLUSIVE'
            if expected=='NORMAL':
                normal += 1
                false_a += r['queue_alarm']=='1'
                false_b += r['label'] not in ('NORMAL','INCONCLUSIVE','IDLE')
        if expected not in ('NORMAL','INCONCLUSIVE'):
            first_a = next((float(r['ts'])-fault['ts'] for r in segment if r['queue_alarm']=='1'), None)
            first_b = next((float(r['ts'])-fault['ts'] for r in segment if r['label']==expected), None)
            detections.append({'label':fault['label'], 'queue_alarm_delay_seconds':first_a,
                               'correct_diagnosis_delay_seconds':first_b})
    result = {'window_confusion_counts':matrix, 'evaluated_windows':classified,
              'window_accuracy_including_inconclusive':correct/classified if classified else None,
              'inconclusive_windows':inconclusive,
              'normal_windows':normal, 'queue_false_alarm_windows':false_a,
              'combined_false_alarm_windows':false_b, 'events':detections,
              'note':'Window accuracy is descriptive; adjacent windows are correlated. Detection delays have polling resolution. Queue baseline cannot classify causes. Repeat independent runs.'}
    atomic_json(folder/'evaluation.json', result)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
