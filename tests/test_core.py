import json
import unittest
from common import percentile
from diagnose import diagnose, StableLabel
from summarize import summarize


class CoreTests(unittest.TestCase):
    def test_percentile(self):
        self.assertIsNone(percentile([],95))
        self.assertAlmostEqual(percentile([10,20,30,40],95),38.5)

    def test_diagnosis_cases(self):
        t = dict(backlog_max=20,p95_max_ms=300,rtt_max_ms=30,processing_max_ms=100)
        s = dict(broker_valid=True,app_valid=True,active=True,consumers=1,
                 probe_valid=True,backlog=0,p95_ms=40,rtt_ms=2,processing_ms=20)
        self.assertEqual(diagnose(s,t)[0],'NORMAL')
        self.assertEqual(diagnose({**s,'backlog':30,'rtt_ms':80},t)[0],'NETWORK_SUSPECTED')
        self.assertEqual(diagnose({**s,'backlog':30,'processing_ms':200},t)[0],'CONSUMER_SLOW_SUSPECTED')
        self.assertEqual(diagnose({**s,'consumers':0,'processing_ms':None},t)[0],'CONSUMER_DOWN')
        self.assertEqual(diagnose({**s,'broker_valid':False},t)[0],'INCONCLUSIVE')
        self.assertEqual(diagnose({**s,'probe_valid':False},t)[0],'INCONCLUSIVE')
        self.assertEqual(diagnose({**s,'backlog':30,'rtt_ms':80,'processing_ms':200},t)[0],'INCONCLUSIVE')
        self.assertEqual(diagnose({**s,'backlog':30},t)[0],'INCONCLUSIVE')

    def test_smoothing(self):
        x=StableLabel(2)
        self.assertEqual(x.update('CONSUMER_DOWN'),'INCONCLUSIVE')
        self.assertEqual(x.update('CONSUMER_DOWN'),'CONSUMER_DOWN')
        self.assertEqual(x.update('NORMAL'),'INCONCLUSIVE')

    def test_summary_duplicate_and_unfinished(self):
        events=[dict(event='attempted',message_id='a',ts=1),dict(event='attempted',message_id='b',ts=2),
                dict(event='confirmed',message_id='a',ts=1),dict(event='confirmed',message_id='b',ts=2),
                dict(event='completed',message_id='a',ts=3,latency_ms=20),
                dict(event='duplicate',message_id='a',ts=4)]
        r=summarize(events,dict(run_id='test',start_ts=0,duration=10,status='finished'))
        self.assertEqual(r['completed_unique_including_drain'],1)
        self.assertEqual(r['confirmed_unfinished_ids'],['b'])
        self.assertEqual(r['duplicates'],1)
        self.assertEqual(r['completed_rate_in_publish_window'],.1)
        self.assertEqual(r['unfinished_count'], 1)
        self.assertEqual(r['unfinished_ratio'], 0.5)
        self.assertTrue(r['survivorship_bias_detected'])

    def test_survivorship_bias_penalty(self):
        # 10 confirmed messages: 8 complete at 40ms, 2 unfinished (20% loss/timeout)
        events = [dict(event='attempted', message_id=f'm{i}', ts=i) for i in range(10)]
        events += [dict(event='confirmed', message_id=f'm{i}', ts=i) for i in range(10)]
        for i in range(8):
            events.append(dict(event='completed', message_id=f'm{i}', ts=i + 0.04, latency_ms=40.0))
        r = summarize(events, dict(run_id='pen_test', start_ts=0, duration=10, drain_seconds=20, status='finished'))
        # Survivors only report 40ms (deceptive)
        self.assertEqual(r['p95_ms_completed_cohort'], 40.0)
        # Penalized p95 lands on the 30,000ms timeout ceiling (revealing failure)
        self.assertEqual(r['p95_ms_with_timeout_penalty'], 30000.0)
        self.assertEqual(r['unfinished_count'], 2)
        self.assertEqual(r['unfinished_ratio'], 0.2)

    def test_calibration_calculation(self):
        from calibrate import compute_calibrated_thresholds
        snaps = [
            {'active': True, 'broker_valid': True, 'app_valid': True, 'probe_valid': True,
             'rtt_ms': 2.0, 'processing_ms': 20.0, 'p95_ms': 30.0, 'backlog': 1},
            {'active': True, 'broker_valid': True, 'app_valid': True, 'probe_valid': True,
             'rtt_ms': 2.2, 'processing_ms': 20.5, 'p95_ms': 31.0, 'backlog': 2},
            {'active': True, 'broker_valid': True, 'app_valid': True, 'probe_valid': True,
             'rtt_ms': 1.8, 'processing_ms': 19.5, 'p95_ms': 29.0, 'backlog': 0}
        ]
        res = compute_calibrated_thresholds(snaps, 'test_base', k=3.0)
        self.assertIn('rtt_max_ms', res)
        self.assertIn('processing_max_ms', res)
        self.assertIn('p95_max_ms', res)
        self.assertIn('backlog_max', res)
        self.assertGreater(res['rtt_max_ms'], 2.0)
        self.assertGreater(res['processing_max_ms'], 20.0)

    def test_littles_law_verification(self):
        # 10 completed messages in 10s -> lambda = 1 msg/s. Latency = 500ms = 0.5s. L = 1 * 0.5 = 0.5
        events = [dict(event='attempted', message_id=f'x{i}', ts=i) for i in range(10)]
        events += [dict(event='confirmed', message_id=f'x{i}', ts=i) for i in range(10)]
        for i in range(10):
            events.append(dict(event='completed', message_id=f'x{i}', ts=i + 0.5, latency_ms=500.0))
        snaps = [{'active': True, 'backlog': 0.3, 'processing_ms': 200.0}]  # in_flight = 1 * 0.2 = 0.2 -> L_obs = 0.5
        r = summarize(events, dict(run_id='little_test', start_ts=0, duration=10, status='finished'), snaps)
        little = r['littles_law']
        self.assertAlmostEqual(little['lambda_completed_rate'], 1.0)
        self.assertAlmostEqual(little['w_mean_latency_seconds'], 0.5)
        self.assertAlmostEqual(little['l_predicted_items'], 0.5)
        self.assertAlmostEqual(little['l_observed_items'], 0.5)
        self.assertAlmostEqual(little['relative_error'], 0.0)
        self.assertEqual(little['status'], 'verified_stationary')

    def test_littles_law_penalized_w(self):
        # 10 confirmed messages: 8 complete at 100ms, 2 unfinished (ceiling = (10+10)*1000 = 20,000ms)
        events = [dict(event='attempted', message_id=f'k{i}', ts=i) for i in range(10)]
        events += [dict(event='confirmed', message_id=f'k{i}', ts=i) for i in range(10)]
        for i in range(8):
            events.append(dict(event='completed', message_id=f'k{i}', ts=i + 0.1, latency_ms=100.0))
        r = summarize(events, dict(run_id='pen_w_test', start_ts=0, duration=10, drain_seconds=10, status='finished'))
        little = r['littles_law']
        # Survivor-only W is 0.1s
        self.assertAlmostEqual(little['w_survivors_mean_latency_seconds'], 0.1)
        # Penalized W is: (8*100 + 2*20000)/10 / 1000 = 4.08s
        self.assertAlmostEqual(little['w_penalized_mean_latency_seconds'], 4.08)
        # Primary W must use penalized W to expose saturation delay
        self.assertAlmostEqual(little['w_mean_latency_seconds'], 4.08)

    def test_producer_limited_detection(self):
        from summarize_sweep import aggregate_sweep
        # Simulate run where target was 100 msg/s, but measured was 40 msg/s due to sync confirms
        run_manifest = {'run_id': 'mock_100', 'rate': 100.0, 'duration': 60}
        run_summary = {
            'offered_rate_in_publish_window': 40.0,
            'completed_rate_in_publish_window': 39.5,
            'p50_ms_completed_cohort': 15.0,
            'p95_ms_completed_cohort': 25.0,
            'p95_ms_with_timeout_penalty': 25.0,
            'p99_ms_with_timeout_penalty': 28.0,
            'unfinished_ratio': 0.01,
            'unfinished_count': 1,
            'confirmed_unfinished_ids': ['mock_100_00000001']
        }
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / 'mock_run'
            f.mkdir()
            (f / 'manifest.json').write_text(json.dumps(run_manifest))
            (f / 'summary.json').write_text(json.dumps(run_summary))
            res = aggregate_sweep([f])
            self.assertEqual(len(res['load_points']), 1)
            point = res['load_points'][0]
            self.assertEqual(point['target_rate'], 100.0)
            self.assertEqual(point['measured_offered_rate'], 40.0)
            self.assertEqual(point['offered_rate'], 40.0)  # Primary x-axis is 40, not 100!
            self.assertTrue(point['producer_limited'])

    def test_link_sweep_models(self):
        from run_link_sweep import run_utilization_delay_sweep, run_loss_tcp_sweep, run_bandwidth_cap_sweep
        # 1. Utilization - M/M/1 model
        u_rows = run_utilization_delay_sweep('127.0.0.1', 5201, 10.0, 1, execute=False)
        self.assertGreater(len(u_rows), 0)
        # As rho increases, delay should monotonically increase
        rtts = [r['rtt_ms'] for r in u_rows]
        self.assertEqual(rtts, sorted(rtts))
        self.assertGreater(u_rows[-1]['rtt_ms'], u_rows[0]['rtt_ms'])

        # 2. Loss - Mathis model
        l_rows = run_loss_tcp_sweep('127.0.0.1', 5201, 1, execute=False)
        self.assertGreater(len(l_rows), 0)
        # Higher loss should reduce TCP throughput
        t_0 = next(r['measured_tcp_mbps'] for r in l_rows if r['netem_loss_pct'] == 0.0)
        t_high = next(r['measured_tcp_mbps'] for r in l_rows if r['netem_loss_pct'] == 10.0)
        self.assertGreater(t_0, t_high)

        # 3. Bandwidth cap
        b_rows = run_bandwidth_cap_sweep('127.0.0.1', 5201, 1, execute=False)
        self.assertEqual(len(b_rows), 6)
        self.assertAlmostEqual(b_rows[0]['tbf_cap_mbps'], 1.0)

    def test_cross_layer_join_logic(self):
        import tempfile
        from cross_layer_join import build_loss_causality_table, build_utilization_causality_table
        with tempfile.TemporaryDirectory() as td:
            loss_tbl = build_loss_causality_table(td, td)
            self.assertGreater(len(loss_tbl), 0)
            self.assertIn('loss_amplification_factor', loss_tbl[0])
            self.assertIn('service_throughput_msg_s', loss_tbl[0])
            self.assertIn('infra_tcp_throughput_mbps', loss_tbl[0])

            util_tbl = build_utilization_causality_table(td, td)
            self.assertGreater(len(util_tbl), 0)
            self.assertIn('link_utilization_rho', util_tbl[0])
            self.assertIn('infra_qdisc_backlog_bytes', util_tbl[0])
            self.assertIn('service_backlog_messages', util_tbl[0])

    def test_zabbix_fidelity_evaluation(self):
        from zabbix_fidelity import generate_or_load_timeseries, evaluate_zabbix_polling_fidelity
        ts = generate_or_load_timeseries(snapshots_file=None, duration=250)
        self.assertEqual(len(ts), 250)
        
        fidelity = evaluate_zabbix_polling_fidelity(ts, poll_intervals=[30, 60], alarm_threshold=30.0)
        self.assertIn('30s', fidelity['polling_intervals'])
        self.assertIn('60s', fidelity['polling_intervals'])
        
        p30 = fidelity['polling_intervals']['30s']
        p60 = fidelity['polling_intervals']['60s']
        # Polling misses or underestimates true peak
        self.assertGreaterEqual(p30['peak_underestimation_pct'], 0.0)
        self.assertGreaterEqual(p60['peak_underestimation_pct'], 0.0)
        # 60s Nyquist minimum resolvable duration is 120s
        self.assertEqual(p60['shannon_nyquist_min_resolvable_burst_sec'], 120)
        self.assertEqual(p30['shannon_nyquist_min_resolvable_burst_sec'], 60)


if __name__ == '__main__':
    unittest.main()
