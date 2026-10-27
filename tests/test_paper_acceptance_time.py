import unittest
from datetime import datetime
from tests import test_paper_live_sync


class AcceptanceTimeTests(unittest.TestCase):
    setUp=test_paper_live_sync.LiveSyncTests.setUp
    tearDown=test_paper_live_sync.LiveSyncTests.tearDown
    snapshot=test_paper_live_sync.LiveSyncTests.snapshot
    cache=test_paper_live_sync.LiveSyncTests.cache
    bar=test_paper_live_sync.LiveSyncTests.bar
    sync=test_paper_live_sync.LiveSyncTests.sync
    day='2026-10-27'
    code='sz000981'

    def submit(self,side='buy',limit='2.32',n=1600):
        self.market_now.return_value=datetime.fromisoformat(self.day+'T13:30:21+08:00')
        q=self.paper.call('paper_quote',dict(code=self.code,stamp=self.day+' 13:28'))
        args=dict(account=self.a,id='time-guard-order',code=self.code,stamp=q['stamp'],token=q['token'],side=side,shares=n,limit_price=limit)
        return self.paper.call('paper_order',args),args

    def sample(self):
        return [self.bar('13:28','2.32',2999700),self.bar('13:29','2.32',127000),self.bar('13:30','2.33',120100),self.bar('13:31','2.33',114900),self.bar('13:32','2.32',144600),self.bar('13:33','2.33',1475700)]

    def test_1328_reference_submitted_133021_cannot_fill_from_1329_or_before(self):
        self.cache(self.sample());order,args=self.submit()
        self.assertEqual(order['stamp'],self.day+' 13:30');self.assertEqual(order['reference_stamp'],self.day+' 13:28')
        self.assertEqual(order['eligible_from'],self.day+' 13:32');self.assertEqual(order['status'],'open')
        self.assertEqual(self.sync('13:30:22')['fill_count'],0)
        self.assertEqual(self.sync('13:32:59')['fill_count'],0)
        s=self.sync('13:33:01');self.assertEqual(s['orders'][0]['filled'],1400)
        self.assertEqual([(f['stamp'],f['price'],f['shares']) for f in s['fills']],[(self.day+' 13:32',232,1400)])
        s=self.sync('13:34:01');self.assertEqual(s['orders'][0]['filled'],1400) # 13:33=2.33 cannot cross a 2.32 buy.
        self.cache(self.sample()+[self.bar('13:34','2.32',100000)])
        s=self.sync('13:35:01');self.assertEqual(s['orders'][0]['status'],'filled')
        points=self.paper.call('paper_chart',dict(account=self.a,code=self.code,start=self.day,end=self.day))['order_points']
        self.assertEqual(len(points),1);self.assertEqual(points[0]['stamp'],self.day+' 13:32');self.assertEqual(points[0]['shares'],1600)
        self.assertEqual(self.paper.call('paper_order',args)['accepted_at'],order['accepted_at'])

    def test_a_233_price_does_not_fill_232_order_regardless_of_old_matching_cache(self):
        self.cache([self.bar('13:28','2.32'),self.bar('13:29','2.32'),self.bar('13:32','2.33'),self.bar('13:33','2.33')])
        self.submit();self.assertEqual(self.sync('13:34:01')['fill_count'],0)

    def test_reference_before_account_clock_is_allowed_without_backdating_order(self):
        self.cache(self.sample());self.market_now.return_value=datetime.fromisoformat(self.day+'T13:30:21+08:00')
        self.paper.call('paper_advance',dict(account=self.a,code=self.code,stamp=self.day+' 13:29'))
        o,_=self.submit();self.assertEqual(o['stamp'],self.day+' 13:30')

    def test_legacy_unfilled_order_uses_recorded_acceptance_time_without_migration(self):
        self.cache(self.sample());o,_=self.submit()
        for key in ['accepted_at','execution_mode','eligible_from','reference_stamp']:o.pop(key)
        o.update(stamp=self.day+' 13:28',last_checked=self.day+' 13:28')
        with self.paper.db:
            self.paper.update_pending(o);state=self.paper.load(self.a);state['clock']=self.day+' 13:28';self.paper.save(state)
        s=self.sync('13:33:01');self.assertEqual(s['orders'][0]['filled'],1400)
        self.assertEqual(s['fills'][0]['stamp'],self.day+' 13:32')

    def test_manual_advance_and_new_orders_cannot_bypass_the_live_cutoff(self):
        self.cache(self.sample());self.submit();before=self.snapshot()
        with self.assertRaisesRegex(ValueError,'当前北京时间之后'):
            self.paper.call('paper_advance',dict(account=self.a,code=self.code,stamp=self.day+' 13:32'))
        self.assertEqual(before,self.snapshot())
        self.paper.call('paper_advance',dict(account=self.a,code=self.code,stamp=self.day+' 13:30'))
        self.assertEqual(self.snapshot()['fill_count'],0)
        self.market_now.return_value=datetime.fromisoformat(self.day+'T13:31:30+08:00')
        q=self.paper.call('paper_quote',dict(code=self.code,stamp=self.day+' 13:28'))
        self.paper.call('paper_order',dict(account=self.a,id='second-current-order',code=self.code,stamp=q['stamp'],token=q['token'],side='buy',shares=100,limit_price='2.32',execution_mode='historical'))
        self.assertEqual(self.snapshot()['fill_count'],0)

    def test_future_cached_reference_is_rejected_with_no_ledger_change(self):
        self.cache(self.sample());self.market_now.return_value=datetime.fromisoformat(self.day+'T13:30:21+08:00')
        q=self.paper.call('paper_quote',dict(code=self.code,stamp=self.day+' 13:32'));before=self.snapshot()
        with self.assertRaisesRegex(ValueError,'未来分钟'):
            self.paper.call('paper_order',dict(account=self.a,id='future-time-order',code=self.code,stamp=q['stamp'],token=q['token'],side='buy',shares=100,limit_price='2.32'))
        self.assertEqual(before,self.snapshot())

    def test_historical_replay_preserves_its_selected_time_when_actual_market_open(self):
        prior='2026-10-26';self.store.cache(self.code,'minute',prior,dict(source='test',volume_unit='shares',bars=self.sample()))
        self.market_now.return_value=datetime.fromisoformat(self.day+'T13:30:21+08:00')
        q=self.paper.call('paper_quote',dict(code=self.code,stamp=prior+' 13:28'))
        o=self.paper.call('paper_order',dict(account=self.a,id='historical-clock',code=self.code,stamp=q['stamp'],token=q['token'],side='buy',shares=100,limit_price='2.32'))
        self.assertEqual(o['execution_mode'],'historical');self.assertEqual(o['stamp'],prior+' 13:28')
        s=self.paper.call('paper_advance',dict(account=self.a,code=self.code,stamp=prior+' 13:29'))
        self.assertEqual(s['fills'][0]['stamp'],prior+' 13:29')

    def test_sell_order_obeys_same_acceptance_boundary(self):
        self.cache([self.bar('13:28','2.34'),self.bar('13:29','2.34'),self.bar('13:32','2.32'),self.bar('13:33','2.34')])
        self.paper.call('paper_seed',dict(account=self.a,code=self.code,shares=100,cost=2))
        self.submit(side='sell',limit='2.33',n=100)
        self.assertEqual(self.sync('13:33:01')['fill_count'],0)
        s=self.sync('13:34:01');self.assertEqual(s['fills'][0]['stamp'],self.day+' 13:33')

    def test_missing_acceptance_timezone_is_insufficient_for_live_fill(self):
        self.cache(self.sample());o,_=self.submit();o['accepted_at']='2026-10-27T13:30:21'
        with self.paper.db:self.paper.update_pending(o)
        self.assertEqual(self.sync('13:34:01')['fill_count'],0)


if __name__=='__main__':unittest.main()
