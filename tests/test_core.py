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


if __name__ == '__main__':
    unittest.main()
