import json

CODES = {'NORMAL': 0, 'NETWORK_SUSPECTED': 1, 'CONSUMER_SLOW_SUSPECTED': 2,
         'CONSUMER_DOWN': 3, 'INCONCLUSIVE': 4, 'IDLE': 5}


def diagnose(s, t):
    if not s.get('broker_valid') or not s.get('app_valid'):
        return 'INCONCLUSIVE', 'Broker/application telemetry unavailable'
    if not s.get('active'):
        return 'IDLE', 'No active run'
    if s.get('consumers') == 0:
        return 'CONSUMER_DOWN', 'Work queue has zero consumers'
    if not s.get('probe_valid') or s.get('processing_ms') is None:
        return 'INCONCLUSIVE', 'Network/processing evidence unavailable'
    bad_app = s['backlog'] > t['backlog_max'] or (
        s.get('p95_ms') is not None and s['p95_ms'] > t['p95_max_ms'])
    bad_net = s['rtt_ms'] > t['rtt_max_ms']
    bad_processing = s['processing_ms'] > t['processing_max_ms']
    if bad_app and bad_net and bad_processing:
        return 'INCONCLUSIVE', 'Both network and processing degraded'
    if bad_app and bad_net:
        return 'NETWORK_SUSPECTED', 'Application degraded; network RTT high'
    if bad_app and bad_processing:
        return 'CONSUMER_SLOW_SUSPECTED', 'Application degraded; service time high'
    if bad_app:
        return 'INCONCLUSIVE', 'Backlog/latency alone does not identify cause'
    return 'NORMAL', 'No degradation above calibrated thresholds'


class StableLabel:
    def __init__(self, windows=2):
        self.windows = windows
        self.last = None
        self.count = 0

    def update(self, label):
        self.count = self.count+1 if label == self.last else 1
        self.last = label
        return label if self.count >= self.windows else 'INCONCLUSIVE'
