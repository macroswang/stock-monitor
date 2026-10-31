import json
import tempfile
import time
import unittest
from datetime import datetime
from unittest.mock import patch

from core.breadth import Breadth, CODE, KIND, historical_available, is_a_share, parse_quotes, summarize
from core.store import Store

DAY = '2026-10-27'
NOW = '2026-10-28T08:00:00+08:00'


def row(code, price, base, volume, stamp=DAY+'T16:14:00+08:00'):
    return dict(code=code, price=str(price), previous_close=str(base), volume=volume, timestamp=stamp)


class BreadthTests(unittest.TestCase):
    def setUp(self):
        patcher = patch('core.breadth.HISTORY', new=__import__('pathlib').Path('/nonexistent-breadth-history.json'))
        patcher.start()
        self.addCleanup(patcher.stop)
        reference = patch('core.breadth.MA_CLOSE_REFERENCE', new=__import__('pathlib').Path('/nonexistent-close-reference.json.gz'))
        reference.start()
        self.addCleanup(reference.stop)
        reference_1030 = patch('core.breadth.MA_CLOSE_REFERENCE_1030', new=__import__('pathlib').Path('/nonexistent-close-reference-1030.json.gz'))
        reference_1030.start()
        self.addCleanup(reference_1030.stop)

    def test_formula_excludes_flat_and_uses_entire_stock_volume(self):
        rows=[row('sh600000',11,10,1000),row('sz000001',12,10,3000),row('sz000002',9,10,6000),row('sz000003',10,10,99999)]
        r=summarize(rows,[x['code'] for x in rows],DAY,NOW)
        self.assertEqual(r['trin'],3)
        self.assertEqual(r['advancing_percent'],50)
        self.assertEqual(r['advancing_volume_percent'],40)
        self.assertEqual(r['flat_volume'],99999)
        self.assertEqual(r['status'],'closed')

    def test_amount_comparison_requires_every_active_stock(self):
        rows=[{**row('a',11,10,1000),'amount_yuan':'11000'},
              {**row('b',9,10,500),'amount_yuan':'4500'},
              {**row('c',10,10,200),'amount_yuan':'2000'}]
        r=summarize(rows,['a','b','c'],DAY,NOW)
        self.assertEqual(r['trin'],.5)
        self.assertAlmostEqual(r['trin_amount'],4500/11000)
        self.assertAlmostEqual(r['advancing_amount_percent'],100*11000/15500)
        missing=[rows[0],row('b',9,10,500),rows[2]]
        r=summarize(missing,['a','b','c'],DAY,NOW)
        self.assertEqual(r['trin'],.5)
        self.assertIsNone(r['trin_amount'])
        self.assertIsNone(r['advancing_amount_percent'])
        invalid=summarize([{**rows[0], 'amount_yuan':'-1'},rows[1],rows[2]],['a','b','c'],DAY,NOW)
        self.assertEqual(invalid['trin'],.5)
        self.assertIsNone(invalid['trin_amount'])

    def test_low_trin_does_not_mean_broad_advance(self):
        rows=[row('up'+str(i),11,10,1000) for i in range(5)]+[row('down'+str(i),9,10,300) for i in range(95)]
        r=summarize(rows,[x['code'] for x in rows],DAY,NOW)
        self.assertAlmostEqual(r['trin'],.3)
        self.assertEqual(r['advancing_percent'],5)
        self.assertLess(r['advancing_volume_percent'],15)

    def test_incomplete_universe_never_publishes_value(self):
        r=summarize([row('sh600000',11,10,100)],['sh600000','sz000001'],DAY,NOW)
        self.assertIsNone(r['trin'])
        self.assertEqual(r['status'],'incomplete')
        self.assertEqual(r['missing_codes'],['sz000001'])

    def test_suspended_and_zero_volume_are_excluded(self):
        rows=[row('a',11,10,200),row('b',9,10,100),row('c',11,10,0)]
        r=summarize(rows,['a','b','c','d'],DAY,NOW,['d'])
        self.assertEqual(r['trin'],.5)
        self.assertEqual(r['suspended'],2)
        self.assertEqual(r['covered'],4)
        self.assertEqual(r['advancing_percent'],50)

    def test_zero_denominator_is_unknown_not_zero_or_infinite(self):
        for rows in ([],[row('a',11,10,100)],[row('a',9,10,100)]):
            r=summarize(rows,[x['code'] for x in rows],DAY,NOW)
            self.assertIsNone(r['trin'])
            self.assertTrue(r['undefined_reason'])

    def test_duplicates_and_mixed_date_rejected(self):
        a=row('a',11,10,100)
        for rows in ([a,a],[row('a',11,10,100,'2026-10-26T16:00:00+08:00')],[row('a',11,10,100,'2026-10-28T16:00:00+08:00')]):
            with self.assertRaises(ValueError):summarize(rows,['a'],DAY,NOW)

    def test_negative_or_nonfinite_volume_rejected(self):
        for bad in (-1,'NaN','Infinity',1.5):
            with self.assertRaises(ValueError):summarize([row('a',11,10,bad)],['a'],DAY,NOW)

    def test_intraday_and_close_finalization_are_separate(self):
        rows=[row('a',11,10,100,DAY+'T10:00:00+08:00'),row('b',9,10,100,DAY+'T10:00:00+08:00')]
        self.assertEqual(summarize(rows,['a','b'],DAY,DAY+'T10:01:00+08:00')['status'],'provisional')
        close=[row('a',11,10,100),row('b',9,10,100)]
        self.assertEqual(summarize(close,['a','b'],DAY,DAY+'T16:15:00+08:00')['status'],'closed')
        self.assertEqual(summarize(rows,['a','b'],DAY,NOW)['status'],'provisional')

    def test_universe_is_shanghai_shenzhen_a_not_watchlist(self):
        for c in ('sh600000','sh688001','sh689009','sz000981','sz301000'):self.assertTrue(is_a_share(c))
        for c in ('sh000001','sh900001','sz200001','bj920001','sh510300'):self.assertFalse(is_a_share(c))

    def test_tencent_volume_units_crosscheck(self):
        def line(code,volume,amount):
            f=['0']*49
            for i,v in {2:code[2:],3:'10',4:'9',6:str(volume),30:'20261027161400',33:'11',34:'9',37:str(amount)}.items():f[i]=v
            return 'v_'+code+'="'+'~'.join(f)+'";'
        text=line('sh600000',100,10)+line('sh688001',10000,10)
        q=parse_quotes(text,{'sh600000','sh688001'})
        self.assertEqual(q['sh600000']['volume'],10000)
        self.assertEqual(q['sh688001']['volume'],10000)
        self.assertEqual(parse_quotes(line('sh688001',100,10),{'sh688001'}),{})

    def test_failures_preserve_cache_and_do_not_change_watch_or_orders(self):
        with tempfile.TemporaryDirectory() as td:
            store=Store(td+'/monitor.sqlite3');store.initialize([('sh600000','示例')],[])
            service=Breadth(store);expected=['a','b']
            result=summarize([row('a',11,10,200),row('b',9,10,100)],expected,DAY,NOW)
            before=store.query('SELECT * FROM watch');config=store.config()
            with patch('core.breadth.collect',return_value=(result,{'public':'raw'})):service.refresh(force=True)
            self.assertEqual(service.view()['days'][0]['trin'],.5)
            with patch('core.breadth.collect',side_effect=OSError()):service.refresh(force=True)
            self.assertEqual(service.view()['days'][0]['trin'],.5)
            self.assertTrue(service.error)
            self.assertEqual(store.query('SELECT * FROM watch'),before)
            self.assertEqual(store.config(),config)
            self.assertEqual(store.query('SELECT * FROM events'),[])
            store.db.close()

    def test_partial_and_downgraded_data_never_replace_closed_day(self):
        with tempfile.TemporaryDirectory() as td:
            store=Store(td+'/monitor.sqlite3');service=Breadth(store)
            r=summarize([row('a',11,10,200),row('b',9,10,100)],['a','b'],DAY,NOW)
            store.cache(CODE,KIND,DAY,r)
            for changed in ({**r,'missing':1},{**r,'status':'provisional'}):
                with patch('core.breadth.collect',return_value=(changed,{})):service.refresh(force=True)
                self.assertEqual(service.view()['days'][0]['status'],'closed')
            store.db.close()

    def test_invalid_closed_cache_can_recover_but_invalid_new_close_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            store=Store(td+'/monitor.sqlite3');service=Breadth(store)
            rows=[row('a',11,10,200),row('b',9,10,100)]
            complete=summarize(rows,['a','b'],DAY,NOW)
            store.cache(CODE,KIND,DAY,{**complete,'missing':1})
            intraday=summarize([row('a',11,10,200,DAY+'T10:00:00+08:00'),
                                row('b',9,10,100,DAY+'T10:00:00+08:00')],
                               ['a','b'],DAY,DAY+'T10:01:00+08:00')
            with patch('core.breadth.collect',return_value=(intraday,{})):
                service.refresh(force=True)
            self.assertEqual(store.getcache(CODE,KIND,DAY)[0]['data']['status'],'provisional')
            with patch('core.breadth.collect',return_value=({**complete,'advance':2},{})):
                service.refresh(force=True)
            self.assertEqual(store.getcache(CODE,KIND,DAY)[0]['data']['status'],'provisional')
            self.assertIn('收盘数据的覆盖或时间异常',service.error)
            with patch('core.breadth.collect',return_value=(complete,{})):
                service.refresh(force=True)
            self.assertEqual(store.getcache(CODE,KIND,DAY)[0]['data']['status'],'closed')
            self.assertEqual(service.error,'')
            store.db.close()

    def test_refresh_cooldown_and_persistence(self):
        with tempfile.TemporaryDirectory() as td:
            store=Store(td+'/monitor.sqlite3');service=Breadth(store)
            r=summarize([row('a',11,10,200),row('b',9,10,100)],['a','b'],DAY,NOW)
            with patch('core.breadth.collect',return_value=(r,{})) as fetch:
                service.refresh();service.refresh();self.assertEqual(fetch.call_count,1)
            self.assertEqual(len(Breadth(store).view()['days']),1)
            store.db.close()

    def test_app_rpc_refresh_is_async_and_keeps_trading_configuration(self):
        from core.app import App
        with tempfile.TemporaryDirectory() as td:
            app=App(td,False)
            before=app.call('snapshot',{})
            r=summarize([row('a',11,10,200),row('b',9,10,100)],['a','b'],DAY,NOW)
            self.assertEqual(app.call('breadth',{})['days'],[])
            with patch('core.breadth.collect',return_value=(r,{})) as fetch:
                for _ in range(2):
                    task=app.call('breadth_refresh',{})
                    for _ in range(100):
                        job=app.call('job',task)
                        if job['status']!='running':break
                        time.sleep(.01)
                    self.assertEqual(job['status'],'done')
                self.assertEqual(fetch.call_count,2)
            self.assertEqual(job['status'],'done')
            self.assertEqual(app.call('breadth',{})['days'][0]['trin'],.5)
            after=app.call('snapshot',{})
            self.assertEqual(after['config'],before['config'])
            self.assertEqual(after['watch'],before['watch'])
            self.assertEqual(after['events'],before['events'])
            self.assertFalse((app.dir/'paper.sqlite3').exists())
            app.store.db.close()

    def test_manual_force_does_not_start_second_concurrent_collection(self):
        with tempfile.TemporaryDirectory() as td:
            store = Store(td+'/monitor.sqlite3')
            service = Breadth(store)
            service.running = True
            with patch('core.breadth.collect') as fetch:
                service.refresh(force=True)
                fetch.assert_not_called()
            self.assertTrue(service.running)
            store.db.close()

class HistoricalBreadthTests(unittest.TestCase):
    def test_history_collection_time_must_be_valid_and_after_close(self):
        now=datetime.fromisoformat('2026-10-31T10:00:00+08:00')
        row={'date':'2026-10-30','status':'closed','historical':True,'collected_at':'2026-10-30T15:00:00+08:00'}
        self.assertTrue(historical_available(row,now))
        for stamp in ('2026-10-30T14:59:59+08:00','2026-10-29T18:00:00+08:00',
                      '2026-10-31T10:00:01+08:00','2026-10-30T15:00:00','bad'):
            self.assertFalse(historical_available({**row,'collected_at':stamp},now),stamp)

    def test_later_backfill_does_not_enter_an_earlier_observation(self):
        with tempfile.TemporaryDirectory() as td:
            store = Store(td+'/monitor.sqlite3')
            with patch('core.breadth.now_cn', return_value=datetime.fromisoformat('2026-10-30T10:00:00+08:00')):
                earlier = Breadth(store).view()['days']
            old = next(r for r in earlier if r['date']=='2026-10-28')
            self.assertEqual(old['mcl_samples'],101)
            self.assertAlmostEqual(old['mcl_standard'],-96.6,places=1)
            self.assertNotIn('2026-10-30',[r['date'] for r in earlier])
            with patch('core.breadth.now_cn', return_value=datetime.fromisoformat('2026-10-31T10:00:00+08:00')):
                intermediate = Breadth(store).view()['days']
            self.assertEqual(next(r for r in intermediate if r['date']=='2026-10-28')['mcl_samples'],141)
            with patch('core.breadth.now_cn', return_value=datetime.fromisoformat('2026-10-31T11:00:00+08:00')):
                later = Breadth(store).view()['days']
            updated = next(r for r in later if r['date']=='2026-10-28')
            self.assertEqual(updated['mcl_samples'],147)
            self.assertAlmostEqual(updated['mcl_standard'],-81.1,places=1)
            self.assertIn('2026-10-30',[r['date'] for r in later])
            store.db.close()

    def test_verified_history_is_sorted_and_does_not_change_cache(self):
        with tempfile.TemporaryDirectory() as td:
            store = Store(td+'/monitor.sqlite3')
            with patch('core.breadth.now_cn', return_value=datetime.fromisoformat('2026-10-30T10:00:00+08:00')):
                rows = Breadth(store).view()['days']
            dates = [r['date'] for r in rows]
            self.assertEqual(dates, sorted(set(dates)))
            self.assertTrue({'2026-03-23','2026-03-24','2026-03-25','2026-10-22','2026-10-23'} <= set(dates))
            oct23 = next(r for r in rows if r['date'] == '2026-10-23')
            self.assertAlmostEqual(oct23['trin'], 1.456961757800716)
            self.assertAlmostEqual(oct23['trin_amount'], 1.066, places=3)
            self.assertTrue(all(r['historical'] for r in rows if r['date'] <= '2026-10-28'))
            reference = next(r for r in rows if r['date'] == '2026-10-29')
            self.assertIn('单来源', reference['reconciliation_note'])
            self.assertEqual(store.getcache(CODE, KIND), [])
            store.db.close()

    def test_live_close_takes_precedence_but_incomplete_does_not_mask_history(self):
        with tempfile.TemporaryDirectory() as td:
            store = Store(td+'/monitor.sqlite3')
            day = '2026-10-23'
            service = Breadth(store)
            count = len(service.view()['days'])
            store.cache(CODE, KIND, day, {'date':day,'status':'incomplete','trin':None})
            self.assertTrue(next(r for r in service.view()['days'] if r['date'] == day)['historical'])
            # An incorrectly marked close must not replace the checked day.
            for bad in ({'date':day,'status':'closed','trin':2},
                        {'date':day,'status':'closed','expected':2,'covered':1,'missing':1,
                         'advance':1,'decline':0,'flat':0,'suspended':0},
                        {'date':'2026-10-22','status':'closed','expected':2,'covered':2,'missing':0,
                         'advance':1,'decline':1,'flat':0,'suspended':0}):
                store.cache(CODE, KIND, day, bad)
                self.assertTrue(next(r for r in service.view()['days'] if r['date'] == day)['historical'])
            close_rows = [row('a',11,10,100,day+'T16:14:00+08:00'),
                          row('b',9,10,200,day+'T16:14:00+08:00')]
            valid_close = summarize(close_rows,['a','b'],day,'2026-10-24T08:00:00+08:00')
            with patch('core.breadth.now_cn', return_value=datetime.fromisoformat('2026-10-31T08:00:00+08:00')):
                for change in ({'first_quote':day+'T14:59:00+08:00'},
                               {'collected_at':'2026-11-01T08:00:00+08:00'},
                               {'first_quote':day+'T16:14:00'},
                               {'last_quote':'2026-10-22T16:14:00+08:00'}):
                    store.cache(CODE,KIND,day,{**valid_close,**change})
                    self.assertTrue(next(r for r in service.view()['days'] if r['date'] == day)['historical'])
            store.cache(CODE, KIND, day, valid_close)
            rows = service.view()['days']
            self.assertEqual(len(rows),count)
            self.assertEqual(next(r for r in rows if r['date'] == day)['trin'],2)
            store.db.close()

if __name__=='__main__':unittest.main()
