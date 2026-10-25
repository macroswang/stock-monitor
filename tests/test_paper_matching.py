import unittest
from tests import test_paper


class LimitMatchingTests(unittest.TestCase):
    setUp=test_paper.PaperTests.setUp
    tearDown=test_paper.PaperTests.tearDown
    snapshot=test_paper.PaperTests.snapshot
    def bars(self, volumes=(10000,10000,10000), prices=('10','9.5','9.4'), day='2026-10-19', **extras):
        self.store.cache('sh600000','minute',day,dict(source='test',volume_unit='shares',bars=[
            dict(time=f'09:{31+i}',close=p,volume=v,complete=True) for i,(v,p) in enumerate(zip(volumes,prices))],**extras))

    def place(self,n=100,price=10,side='buy',stamp='2026-10-19 09:31',key='limit-001'):
        q=self.paper.call('paper_quote',dict(code='sh600000',stamp=stamp))
        return self.paper.call('paper_order',dict(account=self.a,id=key,code=q['code'],stamp=stamp,token=q['token'],side=side,shares=n,limit_price=price))

    def advance(self,time='09:32',day='2026-10-19'):
        return self.paper.call('paper_advance',dict(account=self.a,code='sh600000',stamp=day+' '+time))

    def test_order_never_fills_at_submission_and_freezes_cash(self):
        self.bars();o=self.place()
        s=self.snapshot();self.assertEqual(o['status'],'open');self.assertEqual(s['positions'],[])
        self.assertGreater(s['frozen_cash'],100000);self.assertEqual(s['account']['cash'],10000000)
        s=self.advance();self.assertEqual(s['orders'][0]['status'],'filled');self.assertEqual(s['positions'][0]['shares'],100)
        self.assertEqual(s['fills'][0]['price'],950);self.assertEqual(s['frozen_cash'],0)

    def test_no_crossing_no_fill_even_if_intraminute_low_crosses(self):
        self.bars(prices=('10','11','11'));self.place(price=9.8)
        self.assertEqual(self.advance()['orders'][0]['status'],'open')
        self.assertEqual(self.snapshot()['positions'],[])

    def test_partial_fills_share_volume_and_commission_minimum_once_per_order(self):
        self.bars();self.place(n=200)
        s=self.advance();o=s['orders'][0]
        self.assertEqual(o['status'],'partial');self.assertEqual(o['filled'],100);self.assertEqual(o['commission'],500)
        s=self.advance('09:33');o=s['orders'][0]
        self.assertEqual(o['status'],'filled');self.assertEqual(o['commission'],500)
        self.assertEqual(sum(f['commission'] for f in s['fills']),500)
        self.assertEqual(s['profit'],s['account']['realized']+s['unrealized'])

    def test_pending_cash_prevents_overspending_and_cancel_releases(self):
        self.bars();self.place(n=9900,price=10)
        self.assertEqual(self.place(n=100,price=10,key='limit-002')['status'],'rejected')
        self.paper.call('paper_cancel',dict(account=self.a,id='limit-001'))
        self.assertEqual(self.snapshot()['frozen_cash'],0)
        self.assertEqual(self.place(n=100,key='limit-003')['status'],'open')

    def test_sell_freezes_stock_and_cancel_does_not_undo_partial_fills(self):
        self.bars(prices=('10','11','12'))
        self.paper.call('paper_seed',dict(account=self.a,code='sh600000',shares=300,cost=9))
        self.place(n=200,price=10,side='sell');self.assertEqual(self.snapshot()['positions'][0]['available'],100)
        self.assertEqual(self.place(n=200,side='sell',key='limit-002')['status'],'rejected')
        self.advance();self.paper.call('paper_cancel',dict(account=self.a,id='limit-001'))
        s=self.snapshot();self.assertEqual(s['positions'][0]['shares'],200);self.assertEqual(s['positions'][0]['available'],200)
        self.assertEqual(s['orders'][-1]['filled'],100)

    def test_repeated_submission_and_advance_are_idempotent(self):
        self.bars();self.assertEqual(self.place(),self.place())
        self.advance();before=self.snapshot();self.advance()
        self.assertEqual(self.snapshot()['account']['cash'],before['account']['cash']);self.assertEqual(len(self.snapshot()['fills']),1)

    def test_day_order_does_not_fill_on_next_day(self):
        self.bars(prices=('10','11','11'));self.place(price=9)
        s=self.advance(day='2026-10-20');self.assertEqual(s['orders'][0]['status'],'expired');self.assertEqual(s['positions'],[])
        self.assertEqual(s['frozen_cash'],0)

    def test_volume_budget_is_shared_across_orders_and_price_priority(self):
        self.bars();self.place(n=100,price=10,key='limit-001');self.place(n=100,price=10.1,key='limit-002')
        s=self.advance();orders={o['id']:o for o in s['orders']}
        self.assertEqual(orders['limit-002']['status'],'filled');self.assertEqual(orders['limit-001']['status'],'open')
        self.assertEqual(sum(f['shares'] for f in s['fills']),100)

    def test_known_limit_up_queues_remain_unverified(self):
        self.bars(prices=('10','11','11'),limit_up='11');self.place(price=11)
        self.assertEqual(self.advance()['orders'][0]['status'],'open');self.assertEqual(self.snapshot()['positions'],[])

    def test_unfinished_bar_cannot_match(self):
        self.place();self.assertEqual(self.advance()['orders'][0]['status'],'open')
        # 09:32 close=11 exceeds limit=10; unfinished 09:33 is never consumed.
        self.assertEqual(self.snapshot()['fills'],[])

    def test_zero_volume_can_accept_order_but_not_fill(self):
        self.bars(volumes=(0,0,10000));self.place()
        self.assertEqual(self.advance()['orders'][0]['status'],'open')
        self.assertEqual(self.advance('09:33')['orders'][0]['status'],'filled')

    def test_known_price_bounds_reject_invalid_order(self):
        self.bars(limit_up='11',limit_down='9')
        self.assertEqual(self.place(price=12)['status'],'rejected')
        self.assertEqual(self.snapshot()['frozen_cash'],0)

    def test_chart_uses_only_actual_fills_and_filters_account_code_dates(self):
        self.bars();self.place(n=200)
        args=dict(account=self.a,code='sh600000',start='2026-10-19',end='2026-10-19')
        self.assertEqual(self.paper.call('paper_chart',args)['points'],[])
        self.advance();points=self.paper.call('paper_chart',args)['points']
        self.assertEqual(points[0]['stamp'],'2026-10-19 09:32');self.assertEqual(points[0]['shares'],100)
        self.paper.call('paper_cancel',dict(account=self.a,id='limit-001'))
        self.assertEqual(self.paper.call('paper_chart',args)['points'],points)
        self.assertEqual(self.paper.call('paper_chart',dict(args,code='sz000001'))['points'],[])
        self.assertEqual(self.paper.call('paper_chart',dict(args,start='2026-10-20',end='2026-10-20'))['points'],[])
        account=self.paper.call('paper_create',dict(cash=10000))['id']
        self.assertEqual(self.paper.call('paper_chart',dict(args,account=account))['points'],[])

    def test_history_is_paged_but_totals_export_and_chart_are_complete(self):
        import json
        with self.paper.db:
            for i in range(350):
                o=dict(account=self.a,id=f'bulk-{i}',code='sh600000',stamp='2026-10-19 09:31',side='buy',shares=100,amount=100000,price=1000,fees=500,status='filled',parent_id='test',realized=0)
                self.paper.db.execute('INSERT INTO orders VALUES(?,?,?,?)',(self.a,o['id'],json.dumps(o),'{}'))
                self.paper.index_fill(o)
        snap=self.snapshot();self.assertEqual(len(snap['fills']),200);self.assertEqual(snap['fill_count'],350);self.assertEqual(snap['total_fees'],175000)
        self.assertEqual(len(self.paper.call('paper_export',dict(account=self.a,kind='fills'))),350)
        pts=self.paper.call('paper_chart',dict(account=self.a,code='sh600000',start='2026-10-19',end='2026-10-19'))['points']
        self.assertEqual(len(pts),1);self.assertEqual(pts[0]['shares'],35000)

    def test_execution_index_backfill_does_not_change_original_records(self):
        import json
        from core.paper import Paper
        o=dict(account=self.a,id='legacy-fill',code='sh600000',stamp='2026-10-19 09:31',side='buy',shares=100,amount=100000,price=1000,fees=500,status='filled')
        payload=json.dumps(o)
        with self.paper.db:
            self.paper.db.execute('INSERT INTO orders VALUES(?,?,?,?)',(self.a,o['id'],payload,'{}'))
            self.paper.db.execute("DELETE FROM paper_meta WHERE key='fill_index_v1'")
        self.paper.db.close();self.paper=Paper(self.path/'paper.sqlite3',self.store)
        self.assertEqual(self.paper.db.execute('SELECT payload FROM orders WHERE id=?',(o['id'],)).fetchone()[0],payload)
        self.assertEqual(self.paper.used_shares(self.a,'sh600000',o['stamp']),100)

    def test_daily_chart_is_aggregated_and_linked_intraday_keeps_execution_times(self):
        self.bars();self.place(n=200);self.advance('09:33')
        chart=self.paper.call('paper_chart',dict(account=self.a,code='sh600000',start='2026-10-19',end='2026-10-19',daily=True,day='2026-10-19'))
        self.assertEqual(len(chart['points']),1);self.assertEqual(chart['points'][0]['stamp'],'2026-10-19 00:00')
        self.assertEqual(chart['points'][0]['shares'],200);self.assertEqual(len(chart['minute_points']),2)
        self.assertEqual(chart['minute_points'][0]['stamp'],'2026-10-19 09:32')
