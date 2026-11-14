"""Research engine controls; no candidate performance is asserted."""
import unittest
from datetime import date,timedelta
from research.ma250_optimization import (Portfolio,research_entry,research_exit,next_open_exit,choose_policy)
from research.ma250_execution import net_pct


def bars(n=30):
    days=[];day=date(2026,1,5)
    while len(days)<n:
        if day.weekday()<5:days.append(day.isoformat())
        day+=timedelta(days=1)
    return [dict(date=d,open=10.,close=10.,high=10.3,low=9.8,volume=1000.) for d in days]


def event(bs,entry=0,exit_=2,**extra):
    return dict(code='sh600000',policy='test',signal_date=bs[0]['date'],entry_date=bs[entry]['date'],entry=10.,
                exit_date=bs[exit_]['date'],exit_price=11.,exit_phase='close',factor=1.,strong=True,
                episode_id='episode',stop=9.,sizing='equal',**extra)


class OptimizationControls(unittest.TestCase):
    def test_confirmation_never_enters_before_the_confirmed_close(self):
        bs=bars();bs[1]['close']=10.2;bs[2]['open']=10.25
        f=dict(ma250=[10.]*len(bs),ma5=[10.]*len(bs));s=dict(close=10.,stop=9.)
        e=research_entry('sh600000',bs,f,0,s,'hold2',[b['date'] for b in bs],{b['date']:True for b in bs})
        self.assertEqual(e['index'],2);self.assertEqual(e['price'],10.25)
        original=dict(e);bs.append(dict(bs[-1],date='2026-02-16',open=30.,close=30.,high=31.,low=29.))
        f=dict(ma250=[10.]*len(bs),ma5=[10.]*len(bs))
        self.assertEqual(research_entry('sh600000',bs,f,0,s,'hold2',[b['date'] for b in bs],{b['date']:True for b in bs}),original)

    def test_failed_hold_and_invalid_structure_do_not_buy_later(self):
        bs=bars();f=dict(ma250=[10.]*len(bs),ma5=[10.]*len(bs));s=dict(close=10.,stop=9.)
        bs[2]['close']=12.
        e=research_entry('sh600000',bs,f,0,s,'hold2',[b['date'] for b in bs],{b['date']:True for b in bs})
        self.assertIsNone(e['index'])
        bs[1].update(close=10.2,low=8.9)
        e=research_entry('sh600000',bs,f,0,s,'hold2',[b['date'] for b in bs],{b['date']:True for b in bs})
        self.assertEqual(e['status'],'cancelled_structure')

    def test_breakout_requires_a_completed_close_and_a_later_tradable_open(self):
        bs=bars();bs[1].update(high=10.8,close=10.2)
        bs[2].update(high=10.6,close=10.4);bs[3]['open']=10.5
        f=dict(ma250=[10.]*len(bs),ma5=[10.]*len(bs));s=dict(close=10.,stop=9.)
        args=('sh600000',bs,f,0,s,'break3',[b['date'] for b in bs],{b['date']:True for b in bs})
        e=research_entry(*args)
        self.assertEqual(e['index'],3);self.assertEqual(e['price'],10.5)
        # A high touching the trigger did not fill at that earlier day's open.
        bs[3].update(open=11.44,close=11.44,high=11.44,low=11.44)
        self.assertEqual(research_entry(*args)['status'],'entry_unavailable')

    def test_close_triggered_exit_obeys_t_plus_one_and_locked_days(self):
        bs=bars(5);bs[0]['close']=8.9;bs[1].update(open=8.,close=8.,high=8.,low=8.)
        result=research_exit(bs,dict(ma20=[10.]*5),dict(stop=9.),dict(index=0,price=10.),'invalid20',[b['date'] for b in bs])
        self.assertEqual(result['index'],2);self.assertEqual(result['phase'],'open')
        self.assertEqual(next_open_exit(bs[:2],0)['status'],'pending_exit')

    def test_unknown_twenty_day_horizon_remains_open(self):
        bs=bars(10);r=research_exit(bs,{},dict(stop=9.),dict(index=0,price=10.),'hold20',[b['date'] for b in bs])
        self.assertIsNone(r['date']);self.assertEqual(r['status'],'pending_exit')

    def test_later_cash_cannot_fund_same_opening_entry(self):
        bs=bars(4);es=[]
        for i in range(10):
            e=event(bs,0,1);e.update(code=f'C{i}',exit_phase='open');es.append(e)
        e=event(bs,1,2);e['code']='NEW';es.append(e)
        series={e['code']:bs for e in es};r=Portfolio(series).run(es,details=True)
        self.assertEqual(len(r['trades_detail']),10)
        self.assertNotIn('NEW',{t['code'] for t in r['trades_detail']})

    def test_actual_exit_price_and_costs_determine_realized_net(self):
        bs=bars(4);e=event(bs);r=Portfolio({'sh600000':bs}).run([e],details=True)
        t=r['trades_detail'][0]
        self.assertAlmostEqual(t['net']*100,net_pct(10,11))
        stressed=Portfolio({'sh600000':bs}).run([e],cost=.003,details=True)
        self.assertLess(stressed['trades_detail'][0]['net'],t['net'])

    def test_adjusted_proxy_uses_raw_entry_lots(self):
        bs=bars(4);e=event(bs);e.update(entry=20.,exit_price=22.,factor=2.)
        r=Portfolio({'sh600000':bs}).run([e],details=True)
        self.assertEqual(r['trades_detail'][0]['shares'],4900)
        self.assertAlmostEqual(r['trades_detail'][0]['net']*100,net_pct(20,22))

    def test_selection_rejects_tiny_or_negative_training_samples(self):
        base=dict(trades=20,cagr=1.,win=.5,max_drawdown=-10.)
        self.assertEqual(choose_policy({'B0':base,'tiny':dict(base,trades=2,cagr=100.),'loss':dict(base,cagr=-2.)}),'B0')
        self.assertEqual(choose_policy({'B0':dict(base,cagr=-1.)}),'B0')
        self.assertEqual(choose_policy({'B0':base,'good':dict(base,cagr=2.)}),'good')

if __name__=='__main__':unittest.main()
