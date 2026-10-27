import unittest
from datetime import datetime
from unittest.mock import patch
from tests import test_paper


class LiveSyncTests(unittest.TestCase):
    setUp=test_paper.PaperTests.setUp
    tearDown=test_paper.PaperTests.tearDown
    snapshot=test_paper.PaperTests.snapshot
    day='2026-10-27'
    code='sz000981'

    def cache(self,bars,code=None):
        self.store.remember(code or self.code,'山子高科')
        self.store.cache(code or self.code,'minute',self.day,dict(source='test',volume_unit='shares',bars=bars))

    def bar(self,time,price='2.34',volume=100000,complete=True):
        return dict(time=time,close=price,volume=volume,complete=complete)

    def place(self,side='buy',shares=2000,price='2.35',key='auto-limit-order',code=None):
        code=code or self.code
        self.market_now.return_value=datetime.fromisoformat(self.day+'T10:53:01+08:00')
        q=self.paper.call('paper_quote',dict(code=code,stamp=self.day+' 10:52'))
        return self.paper.call('paper_order',dict(account=self.a,id=key,code=code,stamp=q['stamp'],token=q['token'],side=side,shares=shares,limit_price=price))

    def sync(self,time='11:04:01'):
        self.market_now.return_value=datetime.fromisoformat(self.day+'T'+time+'+08:00')
        return self.paper.call('paper_sync',dict(account=self.a))

    def test_shanzi_limit_order_automatically_fills_from_later_closed_minutes(self):
        self.cache([self.bar('10:52','2.35')]);self.place()
        self.assertEqual(self.snapshot()['orders'][0]['status'],'open')
        self.cache([self.bar('10:52','2.35'),self.bar('10:53','2.35',189500),self.bar('10:54','2.36',137800),self.bar('10:55','2.35',220700),self.bar('10:57','2.34',71300)])
        result=self.sync()
        self.assertEqual(result['orders'][0]['status'],'filled')
        self.assertEqual([(f['stamp'][11:],f['shares'],f['price']) for f in reversed(result['fills'])],[('10:55',2000,235)])
        self.assertEqual(result['positions'][0]['shares'],2000)
        self.assertEqual(result['frozen_cash'],0)
        before=self.snapshot();self.sync();self.assertEqual(before,self.snapshot())

    def test_price_crossing_234_matches_235_and_partial_then_cancel_is_preserved(self):
        self.cache([self.bar('10:52','2.36')]);self.place()
        self.cache([self.bar('10:52','2.36'),self.bar('10:55','2.34',10000)])
        s=self.sync();self.assertEqual(s['orders'][0]['status'],'partial');self.assertEqual(s['fills'][0]['price'],234)
        self.paper.call('paper_cancel',dict(account=self.a,id='auto-limit-order'))
        self.cache([self.bar('10:52','2.36'),self.bar('10:55'),self.bar('10:56')])
        s=self.sync();self.assertEqual(s['positions'][0]['shares'],100);self.assertEqual(s['orders'][0]['status'],'cancelled')
        self.assertEqual(s['frozen_cash'],0)

    def test_future_current_and_unfinished_minutes_never_fill(self):
        self.cache([self.bar('10:52','2.36')]);self.place()
        self.cache([self.bar('10:52','2.36'),self.bar('10:54'),self.bar('10:55',complete=False),self.bar('10:56')])
        s=self.sync('10:55:59');self.assertEqual(s['fill_count'],0)
        s=self.sync('10:56:01');self.assertEqual(s['fill_count'],0)
        self.cache([self.bar('10:52','2.36'),self.bar('10:54'),self.bar('10:55'),self.bar('10:56')])
        s=self.sync('10:56:01');self.assertEqual(s['orders'][0]['filled'],1000);self.assertEqual(s['fills'][0]['stamp'],self.day+' 10:55')

    def test_closed_session_returns_error_reason_without_changing_ledger(self):
        self.cache([self.bar('10:52','2.35')]);self.place()
        self.cache([self.bar('10:52','2.35'),self.bar('10:53')])
        before=self.snapshot()
        for t in ['12:00:00','15:01:00']:
            s=self.sync(t);self.assertEqual(s['sync']['status'],'closed');self.assertIn('禁止模拟委托和成交',s['sync']['message'])
            self.assertEqual(before,self.snapshot())

    def test_historical_replay_is_not_consumed_by_live_timer(self):
        self.cache([self.bar('10:52','2.35')]);self.place()
        self.cache([self.bar('10:52','2.35'),self.bar('10:53')])
        self.market_now.return_value=datetime.fromisoformat('2026-10-28T10:00:00+08:00')
        before=self.snapshot();self.paper.sync_live_accounts()
        s=self.paper.call('paper_sync',dict(account=self.a));self.assertEqual(s['sync']['status'],'historical');self.assertEqual(before,self.snapshot())

    def test_background_processes_all_current_accounts_without_selected_chart(self):
        self.cache([self.bar('10:52','2.36')]);self.place(shares=100)
        a=self.a;self.a=self.paper.call('paper_create',dict(cash=10000))['id'];self.place(shares=100)
        self.cache([self.bar('10:52','2.36'),self.bar('10:55')])
        self.market_now.return_value=datetime.fromisoformat(self.day+'T10:56:01+08:00')
        self.paper.sync_live_accounts()
        for account in [a,self.a]:self.assertEqual(self.paper.call('paper_snapshot',dict(account=account))['fill_count'],1)

    def test_app_background_loop_matches_without_frontend_or_network(self):
        from core.app import App
        self.cache([self.bar('10:52','2.36')]);self.place(shares=100)
        self.cache([self.bar('10:52','2.36'),self.bar('10:55')])
        self.market_now.return_value=datetime.fromisoformat(self.day+'T10:56:01+08:00')
        self.store.setconfig('initialized',True)
        app=App(self.path,False);app.paper=self.paper
        try:
            with patch.object(app.stop,'wait',side_effect=lambda _:app.stop.set()),patch.object(app.provider,'minutes') as network:
                app.paper_loop();network.assert_not_called()
            self.assertEqual(self.snapshot()['orders'][0]['status'],'filled')
        finally:app.store.db.close()

    def test_slow_stock_keeps_unchecked_minutes_until_common_horizon_arrives(self):
        self.cache([self.bar('10:52','2.36')]);self.place(shares=100)
        self.cache([self.bar('10:52','2.36')],code='sh600000');self.place(shares=100,key='other-limit-order',code='sh600000')
        self.cache([self.bar('10:52','2.36'),self.bar('10:55')])
        self.assertEqual(self.sync()['fill_count'],0)
        self.cache([self.bar('10:52','2.36'),self.bar('10:55')],code='sh600000')
        self.assertEqual(self.sync()['fill_count'],2)

    def test_sell_and_buy_limit_prices_and_volume_priority_remain_in_force(self):
        self.cache([self.bar('10:52','2.34')]);self.paper.call('paper_seed',dict(account=self.a,code=self.code,shares=100,cost=2))
        self.place(side='sell',shares=100,price='2.35')
        self.cache([self.bar('10:52','2.34'),self.bar('10:55','2.34')]);self.assertEqual(self.sync()['fill_count'],0)
        self.cache([self.bar('10:52','2.34'),self.bar('10:55','2.34'),self.bar('10:56','2.36')]);s=self.sync()
        self.assertEqual(s['fills'][0]['price'],236);self.assertEqual(s['orders'][0]['status'],'filled')

    def test_session_closure_mid_batch_rolls_back(self):
        self.cache([self.bar('10:52','2.35')]);self.place(shares=100)
        self.cache([self.bar('10:52','2.35'),self.bar('10:55')]);before=self.snapshot()
        with patch('core.paper.trading_error',side_effect=['','','不在交易时间内，禁止模拟委托和成交']):
            with self.assertRaisesRegex(ValueError,'禁止模拟'):self.sync()
        self.assertEqual(before,self.snapshot())

    def test_no_later_data_does_not_query_every_minute_or_write_revision(self):
        self.cache([self.bar('10:52','2.35')]);self.place()
        before=self.snapshot()
        with patch.object(self.paper,'quote',wraps=self.paper.quote) as quote:
            self.sync();self.assertEqual(quote.call_count,1)
        self.assertEqual(before,self.snapshot())


if __name__=='__main__':unittest.main()
