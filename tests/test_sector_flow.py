import tempfile
import unittest
from datetime import datetime,timedelta
from pathlib import Path
from unittest.mock import patch

from core.provider import CN
from core.sector_flow import SectorFlow,expected_day,parse,parse_sina,fetch
from core.store import Store


class SectorFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store=Store(Path(self.tmp.name)/'monitor.sqlite3')
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self.store.db.close)
        self.now=datetime(2026,10,31,13,0,tzinfo=CN)
        self.stamp=datetime(2026,10,30,15,39,30,tzinfo=CN)
        self.rows=[{'f12':f'BK{i:04d}','f14':f'行业{i}','f62':(i-50)*10000,
                    'f66':(i-50)*5000,'f72':(i-50)*5000,'f3':0.5,
                    'f124':int(self.stamp.timestamp())} for i in range(100)]
        self.payload={'data':{'total':len(self.rows),'diff':self.rows}}

    def test_complete_rank_and_quote_date(self):
        r=parse(self.payload,self.now)
        self.assertEqual(r['date'],'2026-10-30');self.assertEqual(len(r['sectors']),100)
        self.assertEqual([x['code'] for x in r['inflow']],['BK0099','BK0098','BK0097'])
        self.assertEqual([x['code'] for x in r['outflow']],['BK0000','BK0001','BK0002'])
        self.assertEqual(expected_day(self.now),'2026-10-30')

    def test_reject_incomplete_duplicate_wrong_dates_and_wrong_sum(self):
        for mutation in ('missing','duplicate','wrong_date','wrong_sum'):
            rows=[dict(x) for x in self.rows]
            if mutation=='missing':rows.pop()
            if mutation=='duplicate':rows[1]['f12']=rows[0]['f12']
            if mutation=='wrong_date':rows[0]['f124']=int((self.stamp-timedelta(days=1)).timestamp())
            if mutation=='wrong_sum':rows[0]['f62']+=100000
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):
                parse({'data':{'total':100,'diff':rows}},self.now)

    def test_intraday_stale_or_future_snapshot_is_rejected(self):
        now=datetime(2026,10,30,10,30,tzinfo=CN)
        for when in (now-timedelta(minutes=4),now+timedelta(minutes=1)):
            rows=[dict(x,f124=int(when.timestamp())) for x in self.rows]
            with self.assertRaises(ValueError):parse({'data':{'total':100,'diff':rows}},now)
        rows=[dict(x,f124=int((now-timedelta(minutes=1)).timestamp())) for x in self.rows]
        self.assertEqual(parse({'data':{'total':100,'diff':rows}},now)['date'],'2026-10-30')

    def test_failed_fetch_does_not_replace_valid_cache(self):
        flow=SectorFlow(self.store,enabled=False)
        with patch('core.sector_flow.now_cn',return_value=self.now),patch('core.sector_flow.fetch',return_value=parse(self.payload,self.now)):
            flow.refresh(force=True)
            self.assertEqual(flow.view()['snapshot']['date'],'2026-10-30')
        with patch('core.sector_flow.now_cn',return_value=self.now),patch('core.sector_flow.fetch',side_effect=OSError('断连')):
            flow.refresh(force=True);report=flow.view()
            self.assertIsNotNone(report['snapshot']);self.assertTrue(report['error'])
        with patch('core.sector_flow.now_cn',return_value=datetime(2026,11,2,10,0,tzinfo=CN)):
            self.assertIsNone(flow.view()['snapshot'])

    def test_cache_collected_in_future_is_not_current(self):
        flow=SectorFlow(self.store,enabled=False);data=parse(self.payload,self.now)
        data['collected_at']=(self.now+timedelta(hours=1)).isoformat()
        self.store.cache('eastmoney-industry','sector_flow_v1',data['date'],data)
        with patch('core.sector_flow.now_cn',return_value=self.now):self.assertIsNone(flow.view()['snapshot'])

    def test_unknown_year_does_not_reuse_last_year_as_current(self):
        self.assertIsNone(expected_day(datetime(2027,1,4,8,0,tzinfo=CN)))

    def test_sina_fallback_requires_same_day_matched_leader_prices(self):
        rows=[];quotes={}
        for i in range(40):
            code=f'sz{i:06d}'
            rows.append(dict(cate_type='0',category=f'new_{i}',name=f'行业{i}',ts_symbol=code,
                             netamount=str((i-20)*100),inamount=str(100000+(i-20)*100),outamount='100000',
                             avg_changeratio='0.01',ts_trade='10.00',ts_changeratio='0'))
            quotes[code]=dict(price='10.00',previous='10.00',stamp=self.stamp)
        data=parse_sina(rows,[],quotes,self.now)
        self.assertEqual(data['source'],'新浪行业资金流')
        self.assertTrue(data['date_inferred']);self.assertIsNone(data['quote_time'])
        self.assertEqual(data['date'],'2026-10-30');self.assertEqual(len(data['anchor_details']),6);self.assertEqual(len(data['sectors']),40)
        self.assertEqual(data['inflow'][0]['code'],'new_39')
        quotes['sz000000']['price']='10.10'
        with self.assertRaisesRegex(ValueError,'未通过核对'):parse_sina(rows,[],quotes,self.now)
        with self.assertRaisesRegex(ValueError,'不完整'):parse_sina(rows,[rows[0]],quotes,self.now)

    def test_provider_failure_uses_separately_labelled_fallback(self):
        fallback={'source':'新浪行业资金流','date_inferred':True}
        with patch('core.sector_flow.fetch_eastmoney',side_effect=OSError('断连')),patch('core.sector_flow.fetch_sina',return_value=fallback):
            self.assertEqual(fetch(self.now),fallback)

    def test_concept_snapshot_requires_matching_kind_and_anchors(self):
        rows=[];quotes={}
        for i in range(40):
            code=f'sz{i:06d}'
            rows.append(dict(cate_type='1',category=f'gn_Concept{i}',name=f'概念{i}',ts_symbol=code,
                             netamount=str((i-20)*100),inamount=str(100000+(i-20)*100),outamount='100000',
                             avg_changeratio='0.01',ts_trade='10.00',ts_changeratio='0'))
            quotes[code]=dict(price='10.00',previous='10.00',stamp=self.stamp)
        data=parse_sina(rows,[],quotes,self.now,'concept')
        self.assertEqual(data['source'],'新浪概念资金流')
        self.assertEqual(data['inflow'][0]['code'],'gn_Concept39')
        self.assertEqual(len(data['anchor_details']),6)
        with self.assertRaises(ValueError):parse_sina(rows,[],quotes,self.now,'industry')
        quotes['sz000000']['stamp']=self.stamp-timedelta(days=1)
        with self.assertRaises(ValueError):parse_sina(rows,[],quotes,self.now,'concept')

    def test_industry_and_concept_cache_are_independent(self):
        industry=SectorFlow(self.store,enabled=False)
        concept=SectorFlow(self.store,enabled=False,kind='concept')
        sector=parse(self.payload,self.now)
        with patch('core.sector_flow.now_cn',return_value=self.now),patch('core.sector_flow.fetch',return_value=sector):
            industry.refresh(force=True)
            self.assertIsNotNone(industry.view()['snapshot'])
            self.assertIsNone(concept.view()['snapshot'])


if __name__=='__main__':unittest.main()
