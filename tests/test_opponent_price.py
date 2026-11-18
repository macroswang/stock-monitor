"""Opponent pricing: native depth + immutable request binding; no real device IO."""
from contextlib import nullcontext
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from decimal import Decimal
import json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from executor.adb import Node
from executor.market_price import OPPONENT_POLICY,MarketPriceError,depth_price,prepare_opponent,validate_selection
from executor.ths_order import read_form
from tests.test_executor_ths_order import form


def depth(prices='2.05 2.04 2.03 2.02 2.01 2.00 1.99 1.98 1.97 1.96'):
 return Node('','com.hexin.plat.android:id/five_buy_sale','android.view.View',(850,250,1070,760),False,True,False,False,description=prices)


def selection(side='buy',price='2.01',code='000981',**changes):
 return dict(policy=OPPONENT_POLICY,side=side,code=code,price=price,book_side='ask1' if side=='buy' else 'bid1',source='ths_native_depth',observed_at=datetime.now(timezone.utc).isoformat(),**changes)


def zhangle_depth_fixture(mid='2.00',spread='.01'):
 mid=Decimal(mid);spread=Decimal(spread);prefix='com.lphtsccft:id/'
 result=[Node('',prefix+'hq_jy_normal_ai_list','android.widget.ListView',(820,300,1060,900),False,True,False,False)]
 for row,(label,value) in enumerate([(f'卖{i}',mid+spread+Decimal('.01')*(i-1)) for i in range(5,0,-1)]+[(f'买{i}',mid-spread-Decimal('.01')*(i-1)) for i in range(1,6)]):
  y=330+row*50
  result += [Node(label,prefix+'hq_jy_normal_ai_label','android.widget.TextView',(840,y,894,y+30),False,True,False,False),Node(format(value,'.2f'),prefix+'hq_jy_normal_ai_price','android.widget.TextView',(894,y,973,y+30),False,True,False,False),Node('6227',prefix+'hq_jy_normal_ai_count','android.widget.TextView',(973,y,1042,y+30),False,True,False,False)]
 return result


class NativeDepthTests(unittest.TestCase):
 def test_observed_zhangle_native_schema_selects_correct_prices(self):
  path=Path(__file__).resolve().parent/'fixtures/zhangle-native-depth.json'
  data=json.loads(path.read_text());nodes=[Node(**n) for n in data['nodes']]
  self.assertTrue(data['quantity_empty']);self.assertEqual(depth_price(nodes,'zhangle','buy'),'2.06');self.assertEqual(depth_price(nodes,'zhangle','sell'),'2.05')
 def test_ths_uses_opposite_side_not_last_price_or_volume(self):
  nodes=[depth('28.25 28.24 28.23 28.22 28.21 28.20 28.19 28.18 28.17 28.16')]
  self.assertEqual(depth_price(nodes,'ths','buy'),'28.21');self.assertEqual(depth_price(nodes,'ths','sell'),'28.20')
 def test_zhangle_uses_bound_label_price_rows_and_ignores_quantities(self):
  nodes=zhangle_depth_fixture()
  self.assertEqual(depth_price(nodes,'zhangle','buy'),'2.01');self.assertEqual(depth_price(nodes,'zhangle','sell'),'1.99')
  for bad in [nodes+[nodes[2]],nodes[:-2],[replace(n,resource_id=n.resource_id.replace('com.lphtsccft','other.app')) for n in nodes]]:
   with self.assertRaises(MarketPriceError):depth_price(bad,'zhangle','buy')
 def test_missing_ambiguous_malformed_crossed_and_wrong_package_are_rejected(self):
  for nodes in [[],[depth(),depth()],[depth('2.01 2.00')],[depth('NaN 2.04 2.03 2.02 2.01 2.00 1.99 1.98 1.97 1.96')],[depth('2.01 2.04 2.03 2.02 2.01 2.00 1.99 1.98 1.97 1.96')],[depth('2.05 2.04 2.03 2.02 2.01 2.02 1.99 1.98 1.97 1.96')],[replace(depth(),resource_id='wrong.package:id/five_buy_sale')]]:
   with self.subTest(nodes=nodes),self.assertRaises(MarketPriceError):depth_price(nodes,'ths','buy')
 def test_empty_opponent_does_not_fall_back_to_the_same_side_or_last_price(self):
  with self.assertRaises(MarketPriceError):depth_price([depth('-- -- -- -- -- 2.00 1.99 1.98 1.97 1.96')],'ths','buy')
  self.assertEqual(depth_price([depth('-- -- -- -- -- 2.00 1.99 1.98 1.97 1.96')],'ths','sell'),'2.00')
 def test_native_price_edits_preserve_direction_code_and_quantity(self):
  nodes=form()+[depth()];edits=[]
  def fill(index,value,nodes=None):
   edits.append((index,value));state[4]=replace(state[4],text=value)
  state=list(nodes)
  prepared,_,evidence=prepare_opponent('ths','buy','000981',100,lambda:list(state),read_form,fill)
  self.assertEqual((prepared.price,prepared.quantity),('2.01','100'));self.assertEqual(edits,[(0,'2.01')]);self.assertEqual(validate_selection(evidence,'000981','buy'),'2.01')
 def test_changing_stock_stops_without_touching_price_or_submit(self):
  fill=Mock()
  with self.assertRaises(MarketPriceError):prepare_opponent('ths','buy','603938',100,lambda:form()+[depth()],read_form,fill)
  fill.assert_not_called()
 def test_fast_moving_book_keeps_first_verified_opponent_price(self):
  state=form()+[depth()];edits=[]
  def fill(index,value,nodes=None):
   edits.append((index,value));state[4]=replace(state[4],text=value)
   state[-1]=depth(' '.join(format(Decimal(token)+Decimal('.01'),'.2f') for token in state[-1].description.split()))
  snapshot=Mock(side_effect=lambda:list(state))
  prepared,_,evidence=prepare_opponent('ths','buy','000981',100,snapshot,read_form,fill)
  self.assertEqual(edits,[(0,'2.01')]);self.assertEqual(snapshot.call_count,2)
  self.assertEqual(prepared.price,'2.01');self.assertEqual(evidence['price'],'2.01')
  self.assertEqual(depth_price(state,'ths','buy'),'2.02')
 def test_evidence_rejects_wrong_side_stock_stale_future_and_non_cent_prices(self):
  good=selection()
  for changes in [{'code':'603938'},{'book_side':'bid1'},{'observed_at':(datetime.now(timezone.utc)-timedelta(seconds=10)).isoformat()},{'observed_at':(datetime.now(timezone.utc)+timedelta(seconds=10)).isoformat()},{'price':'2.013'},{'price':'NaN'},{'observed_at':'2026-11-17T10:00:00'}]:
   with self.subTest(changes=changes),self.assertRaises(ValueError):validate_selection({**good,**changes},'000981','buy')


class PriceJournalTests(unittest.TestCase):
 def setUp(self):
  from core.store import Store
  from core.live_trading import LiveTrading
  from executor.brokers.base import BrokerCredentials
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.store=Store(Path(self.temp.name)/'test.sqlite3');self.addCleanup(self.store.db.close)
  LiveTrading(SimpleNamespace(store=self.store,quotes={}))
  self.run='opponent-test-run-0001';self.key='auto_'+self.run
  now=datetime.now(timezone.utc).isoformat()
  self.store.execute('INSERT INTO trading_runs VALUES(?,?,?,?,?,?,?,?,?,?)',(self.run,'a','sz000981','buy','new-signal',now[:10],'processing',json.dumps({'plan':{'price':'2.00','quantity':100}}),now,now))
  self.client=Mock();self.client.spec.supports_order=True;self.client.ensure_ready.return_value={'account_verified':True}
  for p in [patch('core.brokers.device_operation',return_value=nullcontext()),patch('core.brokers._adapter',return_value=({},BrokerCredentials('ths','123456789'),self.client))]:p.start();self.addCleanup(p.stop)
  self.hook=Mock();self.authorize=Mock()
 def submit(self,**changes):
  from core import brokers
  args=dict(store=self.store,account_id='a',side='buy',code='000981',quantity=100,price='2.00',max_value=None,request_id=self.key,price_policy=OPPONENT_POLICY,on_price=self.hook,authorize=self.authorize);args.update(changes);return brokers.submit_order(**args)
 def test_resolved_price_is_durable_before_the_first_submit_boundary(self):
  def submit(**kw):
   kw['on_price'](selection());p=json.loads(self.store.query('SELECT payload FROM broker_requests')[0]['payload']);self.assertEqual(p['price'],'2.01');self.assertEqual(p['intent']['price'],'2.00')
   with patch('executor.market_price.datetime',wraps=datetime) as clock:
    clock.now.return_value=datetime.now(timezone.utc)+timedelta(seconds=6)
    kw['before_confirm']();kw['before_confirm']()
   return dict(status='accepted',submitted=True,confirm=dict(code='000981',side='buy',quantity=100,price='2.01'))
  self.client.submit_order.side_effect=submit
  result=self.submit();self.assertEqual(result['status'],'accepted');self.assertEqual(self.submit(),result);self.client.submit_order.assert_called_once();self.hook.assert_called_once();self.assertEqual(self.authorize.call_count,2)
 def test_unknown_after_binding_never_reloads_the_book_or_resubmits(self):
  def lost(**kw):kw['on_price'](selection());kw['before_confirm']();raise RuntimeError('receipt lost')
  self.client.submit_order.side_effect=lost;first=self.submit();self.assertEqual(first['status'],'unknown');self.assertEqual(self.submit(),first);self.client.submit_order.assert_called_once()
  self.assertEqual(json.loads(self.store.query('SELECT payload FROM broker_requests')[0]['payload'])['price'],'2.01')
 def test_reopened_database_keeps_bound_price_and_will_not_resubmit_unknown(self):
  from core.store import Store
  def lost(**kw):kw['on_price'](selection());kw['before_confirm']();raise RuntimeError('receipt lost')
  self.client.submit_order.side_effect=lost;first=self.submit()
  self.store=Store(Path(self.temp.name)/'test.sqlite3');self.addCleanup(self.store.db.close)
  self.assertEqual(self.submit(),first);self.client.submit_order.assert_called_once()
  record=json.loads(self.store.query('SELECT payload FROM broker_requests')[0]['payload']);self.assertEqual(record['price'],'2.01');self.assertEqual(record['intent']['price'],'2.00')
 def test_a_changed_intent_cannot_reuse_the_same_request(self):
  self.client.submit_order.side_effect=lambda **kw:{'status':'rejected','submitted':False}
  self.submit()
  with self.assertRaises(ValueError):self.submit(price='2.02')
  with self.assertRaises(ValueError):self.submit(quantity=200)
  self.client.submit_order.assert_called_once()
 def test_missing_binding_cannot_cross_submit_boundary(self):
  self.client.submit_order.side_effect=lambda **kw:kw['before_confirm']()
  result=self.submit();self.assertEqual(result['status'],'failed');self.authorize.assert_not_called()
 def test_funds_or_control_rejection_prevents_the_first_submit_callback(self):
  self.hook.side_effect=ValueError('insufficient funds');submitted=Mock()
  def submit(**kw):kw['on_price'](selection());submitted();kw['before_confirm']()
  self.client.submit_order.side_effect=submit
  self.assertEqual(self.submit()['status'],'failed');submitted.assert_not_called();self.authorize.assert_not_called()
 def test_same_request_cannot_bind_another_price_after_dispatch(self):
  def submit(**kw):kw['on_price'](selection());kw['before_confirm']();kw['on_price'](selection(price='2.02'))
  self.client.submit_order.side_effect=submit;self.assertEqual(self.submit()['status'],'unknown');self.assertEqual(self.hook.call_count,1)
 def test_only_new_automatic_requests_can_enable_opponent_selection(self):
  with self.assertRaises(ValueError):self.submit(request_id='manual-test-order-0001')
  self.client.submit_order.assert_not_called()
 def test_adapter_cannot_claim_acceptance_without_durable_price_and_dispatch(self):
  self.client.submit_order.return_value=dict(status='accepted',submitted=True)
  first=self.submit();self.assertEqual(first['status'],'unknown');self.assertEqual(self.submit(),first);self.client.submit_order.assert_called_once()
 def test_existing_legacy_pending_request_is_not_repriced_or_sent(self):
  old=dict(account_id='a',side='buy',code='000981',quantity=100,price='2.00',max_value=None,dry_run=False)
  stamp=datetime.now(timezone.utc).isoformat()
  self.store.execute('INSERT INTO broker_requests VALUES(?,?,?,?,?,?,?)',(self.key,'a',json.dumps(old,sort_keys=True),'unknown',json.dumps(dict(status='unknown',submitted=False)),stamp,stamp))
  with self.assertRaisesRegex(ValueError,'同一请求号'):self.submit()
  self.assertEqual(json.loads(self.store.query('SELECT payload FROM broker_requests')[0]['payload']),old);self.client.submit_order.assert_not_called();self.hook.assert_not_called()


class ActualExecutionPriceTests(unittest.TestCase):
 def setUp(self):
  from tests.test_trading_price import IncidentExecutionTests
  self.fixture=IncidentExecutionTests('test_falling_buy_is_allowed_and_still_checks_target_holdings');self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
 def execute_case(self,side,actual,funds='100000'):
  f=self.fixture;f.observe(side)
  def submit(*args,**kw):
   kw['on_price'](selection(side=side,price=actual,code='603938'));kw['authorize']();return {'status':'accepted','submitted':True}
  f.submit.side_effect=submit
  snap=f.snapshot();snap['funds']['available']=funds
  with patch('core.live_trading.brokers.holdings',return_value=snap):f.service.drain(reports=False)
  return f.run_payload()
 def test_buy_uses_actual_ask_price_in_plan_and_cost(self):
  row,payload=self.execute_case('buy','29.09');self.assertEqual(row['status'],'accepted');self.assertEqual(payload['plan']['price'],'29.09');self.assertEqual(payload['plan']['value'],5818);self.assertEqual(payload['price_checks']['before_submit']['order_price'],'29.09')
 def test_sell_uses_actual_bid_price_in_plan_and_journal_checks(self):
  row,payload=self.execute_case('sell','29.07');self.assertEqual(row['status'],'accepted');self.assertEqual(payload['plan']['price'],'29.07');self.assertEqual(payload['price_selection']['book_side'],'bid1')
 def test_ask_price_rechecks_affordability_without_changing_quantity(self):
  row,payload=self.execute_case('buy','30.00',funds='5825');self.assertEqual(row['status'],'skipped');self.assertIn('可用资金不足',payload['message']);self.assertEqual(payload['plan']['quantity'],200)
 def test_selected_price_cannot_cross_existing_daily_bounds(self):
  self.fixture.app.quotes[self.fixture.code].update(limit_up='31.94',limit_down='26.14')
  row,payload=self.execute_case('buy','32.00');self.assertEqual(row['status'],'skipped');self.assertIn('涨停价',payload['message']);self.assertFalse(payload['price_checks']['before_submit']['allowed'])
 def test_trial_never_reads_broker_depth_or_binds_an_actual_price(self):
  f=self.fixture;f.store.setconfig('trading_mode','trial');f.observe('buy')
  with patch('core.live_trading.brokers.holdings',return_value=f.snapshot()):f.service.drain(reports=False)
  row,payload=f.run_payload();self.assertEqual(row['status'],'trial');self.assertEqual(payload['plan']['price'],'29.08');self.assertNotIn('price_selection',payload);f.submit.assert_not_called()


class ActualPairedPriceTests(unittest.TestCase):
 def test_actual_ask_must_still_pass_existing_paired_profit_threshold(self):
  from tests.test_paired_t import PairedTTests
  f=PairedTTests('test_live_cycle_survives_trial_switch_and_resumes_only_in_live');f.setUp();self.addCleanup(f.doCleanups)
  f.filled_sell();f.now+=timedelta(minutes=1);f.signal('bottom','profitable-estimate',2.15)
  crossed=Mock()
  def submit(*args,**kwargs):kwargs['on_price'](selection(code='000981',price='2.19'));crossed();kwargs['authorize']();return dict(status='accepted',submitted=True)
  with patch('core.live_trading.brokers.submit_order',side_effect=submit):f.drain()
  row=f.store.query("SELECT * FROM trading_runs WHERE side='buy'")[0];payload=json.loads(row['payload'])
  self.assertEqual(row['status'],'skipped');self.assertIn('净收益',payload['message']);self.assertFalse(payload['profit_gate']['allowed']);self.assertEqual(payload['plan']['quantity'],1000);crossed.assert_not_called()


class NativeOpponentSubmitTests(unittest.TestCase):
 def setUp(self):
  from tests.automatic_e2e_backend import forbidden,poll
  for name,callback in [('executor.adb.Adb.run',forbidden),('executor.trade.wait_until',poll),('executor.ths_order.wait_until',poll)]:
   p=patch(name,side_effect=callback);p.start();self.addCleanup(p.stop)
 def broker(self,kind):
  from tests.automatic_e2e_backend import NativeBroker,Adapter
  owner=NativeBroker(kind,'1234561001',[datetime.now(timezone.utc)],1000);owner.depth_spread='.01';owner.depth_mid='2.24'
  return owner,Adapter(owner)
 def submit(self,adapter,side,hook,guard):
  return adapter.submit_order(side,'000981',100,'2.10',max_value=None,price_policy=OPPONENT_POLICY,on_price=hook,before_confirm=guard)
 def test_both_native_brokers_buy_ask1_and_sell_bid1_before_exact_confirmation(self):
  for kind in ('zhangle','ths'):
   for side,price in [('buy','2.25'),('sell','2.23')]:
    with self.subTest(kind=kind,side=side):
     owner,adapter=self.broker(kind);hook=Mock();guard=Mock()
     type_input=owner.device.input_text
     def move_book(value):
      type_input(value)
      if value==price:
       owner.device.depth_mid='2.35'
     with patch.object(owner.device,'input_text',side_effect=move_book) as typed:
      result=self.submit(adapter,side,hook,guard)
     self.assertNotIn('2.10',[call.args[0] for call in typed.call_args_list])
     self.assertEqual(owner.device.depth_mid,'2.35')
     self.assertEqual(result['status'],'accepted');self.assertEqual(result['confirm']['price'],price);self.assertEqual(owner.orders[0]['price'],price);self.assertEqual(owner.orders[0]['quantity'],100)
     hook.assert_called_once();self.assertEqual(hook.call_args.args[0]['price'],price);self.assertEqual(guard.call_count,1 if kind=='ths' else 2)
 def test_missing_depth_stops_both_native_brokers_before_first_order_tap(self):
  for kind in ('zhangle','ths'):
   with self.subTest(kind=kind):
    owner,adapter=self.broker(kind);hook=Mock();guard=Mock()
    with patch('tests.automatic_e2e_backend.native_depth',return_value=[]),self.assertRaises(MarketPriceError):self.submit(adapter,'buy',hook,guard)
    self.assertEqual(owner.orders,[]);hook.assert_not_called();guard.assert_not_called();self.assertEqual(owner.device.phase,'form')
 def test_changed_confirmation_price_never_gets_final_submit_or_reprice(self):
  for kind in ('zhangle','ths'):
   with self.subTest(kind=kind):
    owner,adapter=self.broker(kind);hook=Mock();guard=Mock();tap=owner.device.tap_node
    # Huatai's initial submit ID is provided by the production adapter.
    from executor.trade import SUBMIT_ID,TradeError
    from executor.ths import ThsError
    def changed(node):
     tap(node)
     if node.resource_id.rsplit('/',1)[-1] in ('btn_transaction',SUBMIT_ID):owner.device.price='2.20'
    with patch.object(owner.device,'tap_node',side_effect=changed),self.assertRaises((TradeError,ThsError)):self.submit(adapter,'buy',hook,guard)
    self.assertEqual(owner.orders,[]);hook.assert_called_once();self.assertEqual(hook.call_args.args[0]['price'],'2.25');self.assertEqual(guard.call_count,0 if kind=='ths' else 1)

 def test_native_failure_before_final_confirmation_has_broker_specific_evidence(self):
  from executor.trade import TradeConfirmationCancelled
  owner,adapter=self.broker('ths');guard=Mock();tap=owner.device.tap_node
  def interrupted(node):
   if node.resource_id.endswith('/btn_transaction'):raise TimeoutError('重连')
   tap(node)
  with patch.object(owner.device,'tap_node',side_effect=interrupted),self.assertRaises(TimeoutError):
   self.submit(adapter,'sell',Mock(),guard)
  guard.assert_not_called()
  self.assertEqual(owner.orders,[])

  owner,adapter=self.broker('zhangle')
  guard=Mock(side_effect=[None,TimeoutError('行情等待更新')])
  with self.assertRaises(TradeConfirmationCancelled):
   self.submit(adapter,'sell',Mock(),guard)
  self.assertEqual(owner.orders,[])
  self.assertEqual(owner.device.phase,'form')
