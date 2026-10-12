import argparse
import json
import threading
import time
from pathlib import Path
import pika
from common import atomic_json, connect, load_env, log, topology, utc


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--run-id', required=True)
    p.add_argument('--rate', type=float, default=5)
    p.add_argument('--duration', type=float, default=60)
    p.add_argument('--payload-bytes', type=int, default=1024)
    p.add_argument('--drain-seconds', type=float, default=60)
    p.add_argument('--max-outstanding', type=int, default=10000)
    a = p.parse_args()
    if not a.run_id.replace('_', '').replace('-', '').isalnum():
        p.error('run-id: letters, digits, underscore or hyphen only')
    if not (0 < a.rate <= 10000 and 0 < a.duration <= 3600 and 0 <= a.drain_seconds <= 600
            and 0 <= a.payload_bytes <= 1048576 and a.max_outstanding >= 1
            and a.rate*a.duration <= 2000000):
        p.error('Invalid or excessively large load parameters')
    load_env()
    folder = Path('data/runs')/a.run_id
    if folder.exists():
        p.error('run-id already exists. Use a NEW run-id; existing logs are preserved.')
    folder.mkdir(parents=True)
    events = folder/'events.jsonl'
    lock = threading.Lock()
    ready, stop = threading.Event(), threading.Event()
    starts, done, confirmed = {}, set(), set()
    receiver_errors = []

    def receive_results():
        while not stop.is_set():
            c = None
            try:
                c = connect()
                ch = c.channel()
                topology(ch)
                ch.basic_qos(prefetch_count=100)
                ready.set()
                for method, props, body in ch.consume('result_queue', inactivity_timeout=1, auto_ack=False):
                    if stop.is_set():
                        break
                    if method is None:
                        continue
                    try:
                        value = json.loads(body)
                        mid = value['message_id']
                        with lock:
                            if value.get('run_id') != a.run_id or mid not in starts:
                                log(events, event='foreign_result', message_id=mid)
                            elif mid in done:
                                log(events, event='duplicate', message_id=mid)
                            else:
                                elapsed = (time.perf_counter()-starts[mid])*1000
                                log(events, event='completed', message_id=mid, latency_ms=elapsed,
                                    processing_ms=value['processing_ms'], worker_id=value.get('worker_id'))
                                done.add(mid)
                    except (ValueError, TypeError, KeyError) as error:
                        with lock:
                            log(events, event='invalid_result', error=str(error))
                    ch.basic_ack(method.delivery_tag)
                ch.cancel()
            except (pika.exceptions.AMQPError, OSError) as error:
                receiver_errors.append(str(error))
                with lock:
                    log(events, event='receiver_error', error=str(error))
                stop.wait(2)
            finally:
                if c and c.is_open:
                    c.close()

    def heartbeat():
        while not stop.is_set():
            atomic_json(folder/'heartbeat.json', {'ts': time.time()})
            stop.wait(1)

    threading.Thread(target=heartbeat, daemon=True).start()
    thread = threading.Thread(target=receive_results, daemon=True)
    thread.start()
    if not ready.wait(20):
        stop.set()
        raise SystemExit('Cannot connect result receiver. Check .env, IP, credentials and broker.')
    c = None
    measured_start = time.time()
    start = time.perf_counter()
    interrupted = False
    atomic_json(folder/'manifest.json', {**vars(a), 'start_utc': utc(), 'start_ts': measured_start,
                                       'status': 'running', 'payload_definition': 'ASCII payload only; JSON overhead excluded'})
    try:
        c = connect()
        ch = c.channel()
        topology(ch)
        ch.confirm_delivery()
        start = time.perf_counter()
        measured_start = time.time()
        atomic_json(folder/'manifest.json', {**vars(a), 'start_utc': utc(), 'start_ts': measured_start,
                                           'status': 'running', 'payload_definition': 'ASCII payload only; JSON overhead excluded'})
        for i in range(int(a.rate*a.duration)):
            due = start+i/a.rate
            while time.perf_counter() < due:
                c.process_data_events(time_limit=min(.05, due-time.perf_counter()))
            if time.perf_counter()-start >= a.duration:
                break
            mid = a.run_id+'_'+str(i+1).zfill(8)
            with lock:
                if len(starts)-len(done) >= a.max_outstanding:
                    log(events, event='load_limited', slot=i)
                    continue
                starts[mid] = time.perf_counter()
                log(events, event='attempted', message_id=mid)
            try:
                ch.basic_publish(exchange='work_exchange', routing_key='work', mandatory=True,
                                 body=json.dumps({'run_id': a.run_id, 'message_id': mid,
                                                  'payload': 'x'*a.payload_bytes}).encode(),
                                 properties=pika.BasicProperties(delivery_mode=2, content_type='application/json'))
                with lock:
                    confirmed.add(mid)
                    log(events, event='confirmed', message_id=mid)
            except pika.exceptions.AMQPError as error:
                with lock:
                    log(events, event='publish_failed_or_unknown', message_id=mid, error=str(error))
                if not c.is_open or not ch.is_open:
                    raise
        while time.perf_counter()-start < a.duration:
            c.process_data_events(time_limit=.1)
        print('Publishing finished; waiting for results...', flush=True)
        deadline = time.perf_counter()+a.drain_seconds
        while time.perf_counter() < deadline:
            with lock:
                if confirmed.issubset(done):
                    break
            c.process_data_events(time_limit=.2)
    except (KeyboardInterrupt, pika.exceptions.AMQPError, OSError) as error:
        interrupted = True
        with lock:
            log(events, event='aborted', error=str(error))
        print('Run aborted:', error, flush=True)
    finally:
        stop.set()
        thread.join(timeout=18)
        if c and c.is_open:
            c.close()
        with lock:
            report = {'run_id': a.run_id, 'confirmed': len(confirmed), 'completed_unique': len(done),
                      'confirmed_unfinished_ids': sorted(confirmed-done),
                      'completed_without_confirm_ids': sorted(done-confirmed),
                      'receiver_errors': len(receiver_errors), 'aborted': interrupted,
                      'receiver_stopped': not thread.is_alive()}
            atomic_json(folder/'status.json', report)
        manifest = json.loads((folder/'manifest.json').read_text())
        manifest.update(status='aborted' if interrupted else 'finished', end_ts=time.time())
        atomic_json(folder/'manifest.json', manifest)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print('Next: python summarize.py --run-id', a.run_id)


if __name__ == '__main__':
    main()
