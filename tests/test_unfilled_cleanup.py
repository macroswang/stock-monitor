"""Read-only, next-session marker cleanup; never cancels or settles orders."""
import json,unittest
from datetime import datetime
from unittest.mock import patch
from core.trading_chart import chart

class UnfilledCleanupTests(unittest.TestCase):
 def setUp(self):
  from tests.test_trading_chart import TradingChartTests
  self.fixture=TradingChartTests('test_chart_is_read_only_and_never_calls_device_or_order_gateway');self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
  self.store=self.fixture.store;self.day='2026-11-13'
 def seed(self,status='accepted',filled=0,observed='2026-11-13T15:05:00+08:00',**changes):
  v=dict(origin='broker_auto',status=status,filled=filled,order_id='contract-one',at=observed,observed_at=observed,source='native_contract',evidence_hash='a'*64);v.update(changes)
  self.fixture.seed(day=self.day,status=status,verification=v)
  row=self.store.query('SELECT * FROM trading_runs')[0];p=json.loads(row['payload']);p['plan']['side']='buy';p['reconciliation']=dict(ok=True,at=observed)
  ack=dict(status=status,submitted=True,order_id='contract-one',verification=v,reconciliation=dict(ok=True,at=observed))
  self.store.execute('UPDATE trading_runs SET payload=?',(json.dumps(p),));self.store.execute('UPDATE broker_requests SET result=?',(json.dumps(ack),))
 def points(self,stamp='2026-11-16T09:00:00+08:00'):
  with patch('core.trading_chart.now_cn',return_value=datetime.fromisoformat(stamp)):
   return chart(self.store,'sz000981',self.day)['points']
 def test_post_close_verified_zero_is_hidden_only_from_next_exchange_session(self):
  self.seed()
  for stamp in ['2026-11-13T15:06:00+08:00','2026-11-14T10:00:00+08:00','2026-11-15T10:00:00+08:00']:
   self.assertNotIn('archived_unfilled',self.points(stamp)[0])
  self.assertTrue(self.points()[0]['archived_unfilled'])
 def test_intraday_zero_acknowledgement_does_not_prove_end_of_day_non_execution(self):
  self.seed(observed='2026-11-13T14:00:00+08:00');self.assertNotIn('archived_unfilled',self.points()[0])
 def test_partial_filled_and_unknown_orders_are_never_cleared(self):
  for status,filled in [('partial',100),('filled',2300),('unknown',0)]:
   with self.subTest(status=status):
    self.store.execute('DELETE FROM trading_runs');self.store.execute('DELETE FROM broker_requests');self.seed(status,filled)
    self.assertNotIn('archived_unfilled',self.points()[0])
 def test_terminal_zero_can_be_cleared_without_waiting_for_a_post_close_snapshot(self):
  for status in ('cancelled','rejected'):
   with self.subTest(status=status):
    self.store.execute('DELETE FROM trading_runs');self.store.execute('DELETE FROM broker_requests');self.seed(status,0,'2026-11-13T14:00:00+08:00')
    self.assertTrue(self.points()[0]['archived_unfilled'])
 def test_missing_future_naive_or_mismatched_evidence_cannot_hide_a_point(self):
  for changes in [dict(origin='manual'),dict(observed_at='2026-11-16T10:00:00+08:00'),dict(observed_at='2026-11-13T15:05:00'),dict(order_id='other'),dict(evidence_hash=''),dict(at='')]:
   with self.subTest(changes=changes):
    self.store.execute('DELETE FROM trading_runs');self.store.execute('DELETE FROM broker_requests');self.seed(**changes)
    self.assertNotIn('archived_unfilled',self.points()[0])
 def test_bad_plan_or_failed_latest_reconciliation_retains_marker(self):
  self.seed();self.store.execute("UPDATE trading_runs SET payload=json_set(payload,'$.plan.price','2.20')")
  self.assertNotIn('archived_unfilled',self.points()[0])
  self.store.execute("UPDATE trading_runs SET payload=json_set(payload,'$.plan.price','2.16','$.reconciliation.ok',json('false'))")
  self.assertNotIn('archived_unfilled',self.points()[0])
 def test_unknown_calendar_keeps_marker_and_makes_no_weekday_assumption(self):
  self.seed()
  with patch('core.breadth._next_verified_trading_day',return_value=None):self.assertNotIn('archived_unfilled',self.points()[0])
 def test_cleanup_preserves_journals_rules_cycles_and_never_calls_broker(self):
  self.seed();before=list(self.store.db.iterdump());changes=self.store.db.total_changes
  with patch('core.brokers.submit_order',side_effect=AssertionError('submit')),patch('core.brokers.cancel',side_effect=AssertionError('cancel')),patch('core.brokers.order_report',side_effect=AssertionError('read')):
   self.assertTrue(self.points()[0]['archived_unfilled'])
  self.assertEqual(self.store.db.total_changes,changes);self.assertEqual(list(self.store.db.iterdump()),before)
  view=self.fixture.service.view();self.assertEqual(view['runs'][0]['status'],'accepted');self.assertEqual(len(view['runs']),1)
