import argparse
import json
import time
from pathlib import Path
import pika
from common import atomic_json, connect, load_env, log, topology


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--worker-id', default='C1')
    parser.add_argument('--processing-ms', type=float, default=20)
    parser.add_argument('--prefetch', type=int, default=1)
    args = parser.parse_args()
    if not args.worker_id.isalnum() or args.prefetch < 1 or not 0 <= args.processing_ms <= 5000:
        parser.error('worker-id must be alphanumeric; prefetch>=1; processing-ms=0..5000')
    load_env()
    print('Consumer', args.worker_id, 'running. Ctrl+C to stop.', flush=True)
    connection = None
    try:
        while True:
            try:
                connection = connect()
                channel = connection.channel()
                topology(channel)
                channel.basic_qos(prefetch_count=args.prefetch)
                channel.confirm_delivery()

                def receive(ch, method, properties, body):
                    try:
                        request = json.loads(body)
                        run = request['run_id']
                        mid = request['message_id']
                        if not isinstance(run, str) or not isinstance(mid, str):
                            raise ValueError('Invalid ID')
                    except (ValueError, KeyError, TypeError):
                        log('data/consumer_errors.jsonl', event='invalid_request')
                        ch.basic_reject(method.delivery_tag, requeue=False)
                        return
                    delay = args.processing_ms
                    control = Path('processing_ms.txt')
                    if control.exists():
                        try:
                            value = float(control.read_text().strip())
                            if 0 <= value <= 5000:
                                delay = value
                        except ValueError:
                            pass
                    start = time.perf_counter()
                    time.sleep(delay/1000)
                    processing = (time.perf_counter()-start)*1000
                    result = {'run_id': run, 'message_id': mid, 'worker_id': args.worker_id,
                              'processing_ms': processing, 'redelivered': method.redelivered}
                    ch.basic_publish(exchange='result_exchange', routing_key='result',
                                     body=json.dumps(result).encode(), mandatory=True,
                                     properties=pika.BasicProperties(delivery_mode=2, content_type='application/json'))
                    log('data/consumer_'+args.worker_id+'.jsonl', event='processed', **result)
                    atomic_json('data/workers/'+args.worker_id+'.json',
                                {'ts': time.time(), 'processing_ms': processing, 'run_id': run})
                    ch.basic_ack(method.delivery_tag)
                    print(mid, 'processed', round(processing, 2), 'ms', flush=True)

                channel.basic_consume('work_queue', receive, auto_ack=False)
                channel.start_consuming()
            except (pika.exceptions.AMQPError, OSError) as error:
                log('data/consumer_errors.jsonl', event='connection_error', error=str(error))
                print('Connection error; retrying:', error, flush=True)
                if connection and connection.is_open:
                    connection.close()
                time.sleep(2)
    except KeyboardInterrupt:
        print('Stopped. In-flight unacked work can be redelivered.')
    finally:
        if connection and connection.is_open:
            connection.close()


if __name__ == '__main__':
    main()
