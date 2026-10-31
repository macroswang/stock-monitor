import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from core.equity_bond import EquityBond, CODE, KIND, make_row, parse_bonds, parse_sse
from core.provider import CN
from core.store import Store


class EquityBondTests(unittest.TestCase):
    def test_sse_date_and_product_are_validated(self):
        row={'PRODUCT_CODE':'17','TRADE_DATE':'20261028','AVG_PE_RATE':'16.14'}
        self.assertEqual(parse_sse({'result':[row]},'2026-10-28'),16.14)
        for payload in ({'result':[]},{'result':[row,row]}, {'result':[dict(row,TRADE_DATE='20261027')]}, {'result':[dict(row,AVG_PE_RATE='NaN')]}):
            with self.subTest(payload=payload),self.assertRaises(ValueError):parse_sse(payload,'2026-10-28')

    def test_bond_date_volume_and_pages_are_validated(self):
        payload={'head':{'rep_code':'200'},'data':{'pageTotal':1,'total':1,'flagMessage':''},'records':[{'dateString':'2026-10-28','tenRate':'1.6237'}]}
        self.assertEqual(parse_bonds(payload,'2026-10-27','2026-10-28'),{'2026-10-28':1.6237})
        for bad in ({**payload,'data':dict(payload['data'],pageTotal=2)}, {**payload,'data':dict(payload['data'],total=2)}, {**payload,'records':[dict(payload['records'][0],dateString='2026-10-29')]}):
            with self.subTest(bad=bad),self.assertRaises(ValueError):parse_bonds(bad,'2026-10-27','2026-10-28')

    def test_formula_has_consistent_percentage_units(self):
        row=make_row('2026-10-28',16.14,1.6237,'2026-10-29T00:48:44+08:00')
        self.assertAlmostEqual(row['spread'],100/16.14-1.6237)
        for value in (0,-1,True,float('nan')):
            with self.subTest(value=value),self.assertRaises(ValueError):make_row('2026-10-28',value,1.6,'2026-10-29T00:48:44+08:00')

    def test_failure_retains_valid_cache_and_future_collection_is_hidden(self):
        with tempfile.TemporaryDirectory() as root,patch('core.equity_bond.HISTORY',Path('/nonexistent-bond.json')):
            store=Store(Path(root)/'test.sqlite3'); svc=EquityBond(store)
            row=make_row('2026-10-28',16.14,1.6237,'2026-10-28T18:00:00+08:00')
            store.cache(CODE,KIND,row['date'],row)
            with patch('core.equity_bond.eligible_sessions',return_value=['2026-10-28']),patch('core.equity_bond.fetch_bonds',side_effect=OSError('offline')):
                self.assertEqual(svc.view(datetime(2026,10,28,17,tzinfo=CN))['days'],[])
                svc.refresh(datetime(2026,10,28,19,tzinfo=CN))
                result=svc.view(datetime(2026,10,28,19,tzinfo=CN))
            self.assertEqual(len(result['days']),1)
            self.assertIn('获取失败',result['error'])

    def test_invalid_cache_and_missing_sessions_are_visible_as_gaps(self):
        with tempfile.TemporaryDirectory() as root,patch('core.equity_bond.HISTORY',Path('/nonexistent-bond.json')):
            store=Store(Path(root)/'test.sqlite3'); svc=EquityBond(store)
            for day in ('2026-10-23','2026-10-27'):
                row=make_row(day,16,1.6,'2026-10-28T18:00:00+08:00');store.cache(CODE,KIND,day,row)
            bad=make_row('2026-10-28',16,1.6,'2026-10-28T18:00:00+08:00');bad['spread']=99;store.cache(CODE,KIND,bad['date'],bad)
            result=svc.view(datetime(2026,10,28,19,tzinfo=CN))
            self.assertEqual(len(result['days']),2)
            self.assertTrue(result['days'][1]['gap_before'])


if __name__=='__main__':unittest.main()
