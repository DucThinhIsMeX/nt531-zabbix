import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path


def utc():
    return datetime.now(timezone.utc).isoformat()


def load_env(path='.env'):
    from dotenv import load_dotenv
    load_dotenv(path)


def connect():
    import pika
    return pika.BlockingConnection(pika.ConnectionParameters(
        host=os.environ['RABBIT_HOST'],
        port=int(os.getenv('RABBIT_PORT', '5672')),
        virtual_host=os.getenv('RABBIT_VHOST', 'lab'),
        credentials=pika.PlainCredentials(os.environ['RABBIT_USER'], os.environ['RABBIT_PASSWORD']),
        heartbeat=60, socket_timeout=10, stack_timeout=15,
        blocked_connection_timeout=15, connection_attempts=1))


def topology(ch):
    for name in ('work', 'result'):
        ch.exchange_declare(exchange=name+'_exchange', exchange_type='direct', durable=True)
        ch.queue_declare(queue=name+'_queue', durable=True, arguments={'x-queue-type': 'classic'})
        ch.queue_bind(queue=name+'_queue', exchange=name+'_exchange', routing_key=name)


def log(path, **fields):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as f:
        f.write(json.dumps({'utc': utc(), 'ts': time.time(), **fields}, ensure_ascii=False)+'\n')


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    temporary.replace(path)


def percentile(values, p):
    if not values:
        return None
    data = sorted(values)
    index = (len(data)-1)*p/100
    low = int(index)
    high = min(low+1, len(data)-1)
    return data[low]+(data[high]-data[low])*(index-low)


def mean(values):
    cleaned = [v for v in values if v is not None]
    return sum(cleaned)/len(cleaned) if cleaned else None


def stddev(values):
    cleaned = [v for v in values if v is not None]
    if len(cleaned) < 2:
        return 0.0 if len(cleaned) == 1 else None
    m = sum(cleaned)/len(cleaned)
    variance = sum((x-m)**2 for x in cleaned)/(len(cleaned)-1)
    return variance**0.5


def read_events(path):
    if not Path(path).exists():
        return []
    result = []
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        try:
            result.append(json.loads(line))
        except json.JSONDecodeError:
            pass  # File may end with an incomplete line while another process writes.
    return result
