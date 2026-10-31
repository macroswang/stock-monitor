import unittest
from datetime import date

from core.breadth import _next_verified_trading_day
from scripts.research_ma_quote_bridge import replay


class MAQuoteBridgeTests(unittest.TestCase):
    def setUp(self):
        day=date(2026,6,1);self.days=[]
        for _ in range(60):
            self.days.append(day.isoformat());day=_next_verified_trading_day(day)
        self.day=self.days[-1]
        self.raw={'date':self.day,'anchor':self.day+'T15:01:00+08:00','collected_at':self.day+'T15:20:00+08:00',
                  'codes':['sh600001','sh600002','sh600003','sh600004'],'suspended':[],
                  'quotes':[{'code':'sh600001','price':'11','previous_close':'10','volume':100,'timestamp':self.day+'T15:01:00+08:00'},
                            {'code':'sh600002','price':'10','previous_close':'10','volume':100,'timestamp':self.day+'T15:01:00+08:00'},
                            {'code':'sh600003','price':'11','previous_close':'10','volume':100,'timestamp':self.day+'T15:01:00+08:00'},
                            {'code':'sh600004','price':'11','previous_close':'9','volume':100,'timestamp':self.day+'T15:01:00+08:00'}]}
    def read(self,d):
        stocks=['600001.SH','600002.SH','600003.SH','600004.SH']
        if d==self.days[10]:stocks.remove('600003.SH')
        return [dict(symbol=s,close='10',pre_close='10') for s in stocks]

    def test_gaps_and_previous_close_mismatch_are_excluded(self):
        result,_=replay(self.days[:-1],self.read,self.raw)
        self.assertEqual(result['windows']['20'],{'eligible':3,'above':2,'percent':200/3})
        self.assertEqual(result['windows']['60'],{'eligible':2,'above':1,'percent':50.0})
        self.assertEqual(result['excluded']['previous_close_mismatch'],1)

    def test_rejects_incomplete_current_day_or_missing_session(self):
        broken=dict(self.raw);broken['quotes']=self.raw['quotes'][:-1]
        with self.assertRaises(ValueError):replay(self.days[:-1],self.read,broken)
        days=self.days[:-1].copy();days[20]=days[19]
        with self.assertRaises(ValueError):replay(days,self.read,self.raw)

    def test_intraday_is_only_accepted_when_explicitly_requested(self):
        raw={**self.raw,'anchor':self.day+'T10:00:00+08:00','collected_at':self.day+'T10:01:00+08:00',
             'quotes':[{**q,'timestamp':self.day+'T10:00:00+08:00'} for q in self.raw['quotes']]}
        with self.assertRaises(ValueError):replay(self.days[:-1],self.read,raw)
        result,_=replay(self.days[:-1],self.read,raw,required_status='provisional')
        self.assertEqual(result['snapshot_status'],'provisional')

    def test_prior_price_discontinuity_resets_that_stock_window(self):
        def rows(d):
            data=self.read(d)
            if d==self.days[-10]:
                next(r for r in data if r['symbol']=='600001.SH')['pre_close']='9.5'
            return data
        result,_=replay(self.days[:-1],rows,self.raw)
        self.assertEqual(result['excluded']['historical_price_discontinuities'],1)
        self.assertEqual(result['windows']['60']['eligible'],1)
        self.assertEqual(result['windows']['20']['eligible'],2)


if __name__=='__main__':unittest.main()
