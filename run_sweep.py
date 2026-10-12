import argparse
import subprocess
import sys
import time


def main():
    p = argparse.ArgumentParser(description='Run an automated load sweep across multiple offered rates')
    p.add_argument('--prefix', default='sweep', help='Prefix for run IDs (e.g. sweep -> sweep_05, sweep_10...)')
    p.add_argument('--rates', nargs='+', type=float, default=[5, 10, 20, 30, 40, 50, 60],
                   help='List of offered rates in msg/s (default: 5 10 20 30 40 50 60)')
    p.add_argument('--duration', type=float, default=60, help='Publish duration per run in seconds (default: 60)')
    p.add_argument('--drain-seconds', type=float, default=30, help='Drain duration per run in seconds (default: 30)')
    p.add_argument('--payload-bytes', type=int, default=1024, help='Payload size in bytes (default: 1024)')
    p.add_argument('--push-zabbix', action='store_true', help='Push collector telemetry to Zabbix during sweep')
    p.add_argument('--execute', action='store_true', help='Execute runs sequentially (default: print commands)')
    a = p.parse_args()

    run_ids = []
    commands = []
    for rate in a.rates:
        rate_str = f"{int(rate):02d}" if rate.is_integer() else f"{rate:.1f}".replace('.', '_')
        run_id = f"{a.prefix}_{rate_str}"
        run_ids.append(run_id)
        cmd_prod = [sys.executable, 'producer.py', '--run-id', run_id, '--rate', str(rate),
                    '--duration', str(a.duration), '--drain-seconds', str(a.drain_seconds),
                    '--payload-bytes', str(a.payload_bytes)]
        cmd_coll = [sys.executable, 'collector.py', '--run-id', run_id]
        if a.push_zabbix:
            cmd_coll.append('--push-zabbix')
        cmd_sum = [sys.executable, 'summarize.py', '--run-id', run_id]
        commands.append((run_id, rate, cmd_prod, cmd_coll, cmd_sum))

    if not a.execute:
        print(f"--- Load Sweep Plan ({len(commands)} runs) ---")
        print("To execute on Machine A, run with --execute, or execute commands below:\n")
        for rid, rate, c_prod, c_coll, c_sum in commands:
            print(f"# Rate {rate} msg/s -> {rid}")
            print(f"{' '.join(c_prod)} &")
            print(f"PID_P=$!")
            print(f"{' '.join(c_coll)} &")
            print(f"PID_C=$!")
            print("wait $PID_P")
            print("sleep 2; kill -INT $PID_C 2>/dev/null || true")
            print(" ".join(c_sum))
            print("sleep 5\n")
        print("After all runs finish, summarize and plot the sweep with:")
        print(f"python summarize_sweep.py --pattern '{a.prefix}_*'")
        print("python plot_sweep.py\n")
        return

    print(f"Executing Load Sweep of {len(commands)} rates: {a.rates}...")
    for rid, rate, c_prod, c_coll, c_sum in commands:
        print(f"\n==========================================")
        print(f"Starting sweep run {rid} at rate {rate} msg/s (Producer + Collector)")
        print(f"==========================================")
        coll_proc = subprocess.Popen(c_coll)
        try:
            res = subprocess.run(c_prod)
            if res.returncode != 0:
                print(f"Run {rid} failed with code {res.returncode}. Aborting sweep.")
                sys.exit(res.returncode)
        finally:
            time.sleep(2)
            coll_proc.terminate()
            try:
                coll_proc.wait(timeout=6)
            except subprocess.TimeoutExpired:
                coll_proc.kill()

        print(f"Summarizing run {rid} (with snapshots)...")
        subprocess.run(c_sum)
        print("Cooling down 5s before next rate point...")
        time.sleep(5)

    print("\nAll sweep runs completed! Generating aggregated load curves...")
    subprocess.run([sys.executable, 'summarize_sweep.py', '--pattern', f"{a.prefix}_*"])
    subprocess.run([sys.executable, 'plot_sweep.py'])


if __name__ == '__main__':
    main()
