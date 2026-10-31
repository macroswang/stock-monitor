import tempfile
import unittest
from datetime import datetime,timedelta
from pathlib import Path
from unittest.mock import patch
from core.external_market import ExternalMarket,parse
from core.provider import CN
from core.store import Store


def indexed(code,price='100',previous='100',percent='0',stamp='2026-10-30 16:00:00'):
    fields=['']*33
    fields[3]=price;fields[4]=previous;fields[30]=stamp;fields[32]=percent
    return f'v_{code}="'+ '~'.join(fields)+'";'


def commodity(code,price='101',previous='100',percent='1',stamp='2026-10-31'):
    return f'v_{code}="{price},{percent},0,0,0,0,04:00:00,{previous},0,0,0,0,{stamp},name";'


class ExternalMarketTests(unittest.TestCase):
    def setUp(self):self.now=datetime(2026,10,31,17,30,tzinfo=CN)
    def test_parse_valid_prices_and_keep_raw_source_time(self):
        data=parse(indexed('us.IXIC','101','100','1')+commodity('hf_GC'),self.now)
        self.assertEqual([r['code'] for r in data['quotes']],['us.IXIC','hf_GC'])
        self.assertEqual(data['quotes'][0]['source_time'],'2026-10-30 16:00:00')
        self.assertIn('时区及延迟未核实',data['quotes'][0]['time_basis'])
    def test_rejects_future_wrong_percent_malformed_and_old(self):
        for source in (indexed('us.IXIC','101','100','30'),indexed('us.IXIC',stamp='2026-11-01 16:00:00'),indexed('us.IXIC',stamp='2026-10-01 16:00:00'),indexed('us.IXIC','NaN'),commodity('hf_GC',previous='0')):
            with self.subTest(source=source),self.assertRaises(ValueError):parse(source,self.now)
    def test_partial_responses_are_labelled_individually_and_deduplicated(self):
        data=parse(indexed('hkHSI')+indexed('hkHSI')+indexed('unknown'),self.now)
        self.assertEqual(len(data['quotes']),1)
    def test_failure_retains_prior_snapshot_and_marks_error(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(Path(directory)/'test.db')
            try:
                feed=ExternalMarket(store,enabled=False)
                data=parse(indexed('hkHSI'),self.now)
                with patch('core.external_market.now_cn',return_value=self.now),patch('core.external_market.fetch',return_value=data):
                    feed.refresh();self.assertEqual(feed.view()['snapshot']['quotes'][0]['name'],'恒生指数')
                feed.last_attempt=float('-inf')
                with patch('core.external_market.now_cn',return_value=self.now),patch('core.external_market.fetch',side_effect=OSError('断连')):
                    feed.refresh();result=feed.view();self.assertTrue(result['error']);self.assertIsNotNone(result['snapshot'])
                with patch('core.external_market.now_cn',return_value=self.now+timedelta(days=8)):
                    self.assertIsNone(feed.view()['snapshot'])
            finally:store.db.close()


if __name__=='__main__':unittest.main()
