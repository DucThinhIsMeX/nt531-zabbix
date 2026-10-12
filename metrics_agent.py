import argparse
import json
import re
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--broker-ip', required=True)
    p.add_argument('--bind', default='0.0.0.0')
    p.add_argument('--port', type=int, default=9109)
    a = p.parse_args()
    state, lock = {}, threading.Lock()

    def update():
        while True:
            rtt = None
            try:
                proc = subprocess.run(['ping', '-n', '-c', '3', '-W', '2', a.broker_ip],
                                      capture_output=True, text=True, timeout=5, env={'LC_ALL': 'C', 'PATH': '/usr/bin:/bin'})
                times = [float(m) for m in re.findall(r'time[=<]([\d.]+)', proc.stdout)]
                if times:
                    rtt = round(sum(times) / len(times), 2)
            except (OSError, subprocess.TimeoutExpired):
                pass
            workers = []
            for path in Path('data/workers').glob('*.json'):
                try:
                    v = json.loads(path.read_text())
                    if time.time()-v['ts'] <= 30:
                        workers.append(v)
                except (OSError, ValueError, KeyError):
                    pass
            with lock:
                state.clear()
                state.update(ts=time.time(), rtt_ms=rtt, workers=workers)
            time.sleep(3)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != '/metrics':
                self.send_error(404)
                return
            with lock:
                body = json.dumps(state).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    threading.Thread(target=update, daemon=True).start()
    print('Metrics API on port', a.port, 'LAN lab only. Ctrl+C to stop.', flush=True)
    try:
        ThreadingHTTPServer((a.bind, a.port), Handler).serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
