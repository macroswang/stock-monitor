import json
import tempfile
import unittest
from datetime import datetime,timedelta
from pathlib import Path
from unittest.mock import patch
from core import stock_profile as sp
from core.provider import CN
from core.store import Store


class StockProfileTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,11,16,14,0,tzinfo=CN)
        self.code='sh688218'
        names=['机械设备','自动化设备','机器人','江苏板块','小盘股','人形机器人','低空经济','高端装备']
        self.core={'ssbk':[dict(SECUCODE='688218.SH',SECURITY_CODE='688218',BOARD_RANK=i+1,BOARD_NAME=n,BOARD_CODE=str(i)) for i,n in enumerate(names)]}
        for i,row in enumerate(self.core['ssbk']):
            if i<3:row.update(BOARD_TYPE='行业',BOARD_LEVEL=i+1)
            elif i>=5:row.update(IS_PRECISE='1',SELECTED_BOARD_REASON='公司业务证据')
        self.survey={'jbzl':[dict(SECUCODE='688218.SH',SECURITY_CODE='688218',EM2016='机械设备-机器人-工业机器人')]}
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(Path(self.tmp.name)/'data.sqlite3');self.addCleanup(self.store.db.close)
        self.service=sp.StockProfile(self.store,self.tmp.name,enabled=False)

    def data(self):
        with patch.object(sp,'now_cn',return_value=self.now):return sp.parse(self.code,self.core,self.survey)

    def test_classifies_provider_industry_concepts_and_attributes_without_guessing(self):
        data=self.data()
        self.assertEqual(data['industry'],['机械设备','机器人','工业机器人'])
        self.assertEqual([r['name'] for r in data['concepts']],['人形机器人','低空经济','高端装备'])
        self.assertEqual([r['name'] for r in data['attributes']],['小盘股'])
        self.assertEqual([r['name'] for r in data['boards']],['江苏板块'])

    def test_rejects_wrong_stock_in_either_response_and_empty_response(self):
        for part in ['core','survey']:
            core=json.loads(json.dumps(self.core));survey=json.loads(json.dumps(self.survey))
            (core['ssbk'] if part=='core' else survey['jbzl'])[0]['SECURITY_CODE']='600000'
            with self.subTest(part=part),self.assertRaisesRegex(ValueError,'代码不一致'):sp.parse(self.code,core,survey)
        with self.assertRaises(ValueError):sp.parse(self.code,{}, {})

    def test_partial_fetch_retains_available_concepts_without_fabricating_industry(self):
        with patch.object(sp,'_read',side_effect=[self.core,OSError('offline')]):data=sp.fetch(self.code)
        self.assertTrue(data['partial']);self.assertEqual(data['industry'],['机械设备','自动化设备','机器人'])
        self.assertEqual(len(data['concepts']),3)

    def test_valid_cached_profile_is_read_only_and_no_network_is_needed(self):
        self.store.cache(self.code,sp.KIND,'2026-11-16',self.data())
        with patch.object(sp,'now_cn',return_value=self.now),patch.object(sp,'fetch') as fetch:
            result=self.service.view(self.code)
        self.assertEqual(result['data']['code'],self.code);fetch.assert_not_called()
        self.assertEqual(self.store.query('SELECT count(*) AS n FROM events')[0]['n'],0)

    def test_future_expired_or_mismatched_cached_profiles_are_not_exposed(self):
        for mutation in ['future','expired','wrong_code']:
            data=self.data()
            if mutation=='future':data['collected_at']=(self.now+timedelta(seconds=1)).isoformat()
            if mutation=='expired':data['collected_at']=(self.now-timedelta(days=2)).isoformat()
            if mutation=='wrong_code':data['code']='sh600000'
            self.store.cache(self.code,sp.KIND,'2026-11-16',data)
            with patch.object(sp,'now_cn',return_value=self.now):
                self.assertIsNone(self.service.view(self.code)['data'])

    def test_only_current_research_memberships_are_shown_and_future_is_rejected(self):
        folder=Path(self.tmp.name)/'daily-outlook';folder.mkdir()
        issue=dict(quote_date='2026-11-16',published_at=(self.now-timedelta(minutes=1)).isoformat(),
                   themes=[dict(name='具身智能',members=[dict(code=self.code,basis='公司主营业务',source='https://example.org/filing')])],
                   radar=[dict(theme='名称观察',kind='名称/玄学',stocks=[dict(code=self.code)])])
        path=folder/'2026-11-16_135900.json';path.write_text(json.dumps(issue))
        with patch.object(sp,'now_cn',return_value=self.now):
            themes=self.service.view(self.code)['themes']
            self.assertEqual(themes,[dict(name='具身智能',kind='研究题材')])
            self.assertEqual(self.service.view(self.code)['observations'],[dict(name='名称观察',kind='名称/玄学')])
            self.assertEqual(self.service.view('sh600000')['themes'],[])
        with patch.object(sp,'now_cn',return_value=self.now-timedelta(minutes=2)):
            self.assertEqual(self.service.view(self.code)['themes'],[])
        with patch.object(sp,'now_cn',return_value=self.now+timedelta(days=1)):
            self.assertEqual(self.service.view(self.code)['themes'],[])

    def test_metadata_background_work_is_bounded_to_two_without_queuing(self):
        self.service.enabled=True
        with patch.object(sp.threading,'Thread') as thread,patch.object(sp,'now_cn',return_value=self.now):
            for code in ['sh688218','sh600000','sz300364']:
                self.assertTrue(self.service.view(code)['running'])
            self.assertEqual(thread.call_count,2)
            self.assertEqual(self.service.running,{'sh688218','sh600000'})

    def test_rank_is_not_a_classification_and_earnings_are_attributes(self):
        self.core['ssbk'][5]['BOARD_RANK']=1
        self.core['ssbk'][0]['BOARD_RANK']=99
        self.core['ssbk'].extend([
            dict(SECUCODE='688218.SH',SECURITY_CODE='688218',BOARD_NAME='2026中报预增',BOARD_CODE='x',SELECTED_BOARD_REASON='业绩预告',BOARD_RANK=2),
            dict(SECUCODE='688218.SH',SECURITY_CODE='688218',BOARD_NAME='未分类归属',BOARD_CODE='y',BOARD_RANK=1)])
        data=self.data()
        self.assertIn('人形机器人',[r['name'] for r in data['concepts']])
        self.assertNotIn('2026中报预增',[r['name'] for r in data['concepts']])
        self.assertIn('2026中报预增',[r['name'] for r in data['attributes']])
        self.assertNotIn('机械设备',[r['name'] for r in data['concepts']])
        self.assertIn('未分类归属',[r['name'] for r in data['boards']])

    def test_historical_day_never_uses_later_research_and_skips_after_close_report(self):
        folder=Path(self.tmp.name)/'daily-outlook';folder.mkdir()
        def issue(day,hour,name):
            data=dict(quote_date=day,published_at=day+f'T{hour}:00:00+08:00',radar=[dict(theme=name,kind='事件/题材',stocks=[dict(code=self.code)])])
            (folder/f'{day}_{hour}0000.json').write_text(json.dumps(data))
        issue('2026-11-13','14','历史题材');issue('2026-11-13','20','盘后题材');issue('2026-11-16','13','后来题材')
        with patch.object(sp,'now_cn',return_value=self.now):
            self.assertEqual(self.service.view(self.code)['themes'][0]['name'],'后来题材')
            past=self.service.view(self.code,'2026-11-13')
            self.assertEqual(past['themes'],[dict(name='历史题材',kind='事件/题材')])
            self.assertEqual(past['theme_published_at'],'2026-11-13T14:00:00+08:00')
            self.assertEqual(self.service.view(self.code,'2026-11-17')['theme_status'],'unavailable')

    def test_future_or_corrupt_latest_report_does_not_hide_older_valid_report(self):
        folder=Path(self.tmp.name)/'daily-outlook';folder.mkdir()
        for hour,name in [('13','已发布'),('15','尚未发布')]:
            (folder/f'2026-11-16_{hour}0000.json').write_text(json.dumps(dict(quote_date='2026-11-16',published_at=f'2026-11-16T{hour}:00:00+08:00',radar=[dict(theme=name,kind='事件/题材',stocks=[dict(code=self.code)])])))
        with patch.object(sp,'now_cn',return_value=self.now):
            for _ in range(2):self.assertEqual(self.service.view(self.code)['themes'][0]['name'],'已发布')

    def test_incomplete_or_unproven_memberships_are_not_business_themes(self):
        folder=Path(self.tmp.name)/'daily-outlook';folder.mkdir()
        member=dict(code=self.code,basis='主营业务',source='https://example.org/filing')
        themes=[dict(code='topic_bad',name='未核对',error='公告未取得',members=[member]),dict(name='缺证据',members=[dict(code=self.code)]),dict(name='已核对',members=[member])]
        (folder/'2026-11-16_130000.json').write_text(json.dumps(dict(quote_date='2026-11-16',published_at='2026-11-16T13:00:00+08:00',themes=themes,discovery=dict(filing_errors={'topic_bad':'公告未取得'}))))
        with patch.object(sp,'now_cn',return_value=self.now):
            self.assertEqual(self.service.view(self.code)['themes'],[dict(name='已核对',kind='研究题材')])

    def test_unavailable_research_is_distinguished_from_a_valid_no_match(self):
        with patch.object(sp,'now_cn',return_value=self.now):self.assertEqual(self.service.view(self.code)['theme_status'],'unavailable')
        folder=Path(self.tmp.name)/'daily-outlook';folder.mkdir()
        (folder/'2026-11-16_130000.json').write_text(json.dumps(dict(quote_date='2026-11-16',published_at='2026-11-16T13:00:00+08:00',themes=[])))
        with patch.object(sp,'now_cn',return_value=self.now):self.assertEqual(self.service.view(self.code)['theme_status'],'unmatched')

    def test_business_membership_is_independent_of_price_flow_or_peer_entry_gates(self):
        folder=Path(self.tmp.name)/'daily-outlook';folder.mkdir()
        member=dict(code=self.code,basis='公司主营机器人业务',source='https://example.org/filing')
        themes=[dict(name='工业机器人',error='部分公司的同日价格或资金流未核对，本期继续等。',members=[member]),
                dict(name='细分业务',error='已核实1家相关公司，需要至少三家才能比较候选和同行。',members=[member])]
        (folder/'2026-11-16_130000.json').write_text(json.dumps(dict(quote_date='2026-11-16',published_at='2026-11-16T13:00:00+08:00',themes=themes)))
        with patch.object(sp,'now_cn',return_value=self.now):
            self.assertEqual([t['name'] for t in self.service.view(self.code)['themes']],['工业机器人','细分业务'])

    def test_old_schema_and_malformed_cached_lists_are_not_exposed(self):
        for mutation in ['old','malformed']:
            data=self.data()
            if mutation=='old':data.pop('schema_version')
            else:data['concepts']='bad'
            self.store.cache(self.code,sp.KIND,'2026-11-16',data)
            with patch.object(sp,'now_cn',return_value=self.now):self.assertIsNone(self.service.view(self.code)['data'])

    def test_cache_reads_are_indexed_and_bounded(self):
        self.store.cache(self.code,sp.KIND,'2026-11-16',self.data())
        with patch.object(self.store,'query',wraps=self.store.query) as query,patch.object(sp,'now_cn',return_value=self.now):
            self.assertIsNotNone(self.service.view(self.code)['data'])
            self.assertIn('LIMIT 2',query.call_args.args[0])

    def test_catalog_pagination_is_complete_and_count_changes_are_rejected(self):
        from urllib.parse import parse_qs,urlparse
        first=dict(result=dict(count=201,pages=2,data=[dict(BOARD_CODE=str(i)) for i in range(200)]))
        second=dict(result=dict(count=201,pages=2,data=[dict(BOARD_CODE='200')]))
        with patch.object(sp,'_json',side_effect=[first,second]) as get:
            self.assertEqual(len(sp._read('CoreConception',self.code)['ssbk']),201)
            self.assertEqual(parse_qs(urlparse(get.call_args.args[0]).query)['pageNumber'],['2'])
        second['result']['count']=202
        with patch.object(sp,'_json',side_effect=[first,second]),self.assertRaises(ValueError):sp._read('CoreConception',self.code)

    def test_bad_code_is_a_validation_error(self):
        for code in [None,123,'sh000001','other']:
            with self.subTest(code=code),self.assertRaises(ValueError):self.service.view(code)


if __name__=='__main__':unittest.main()
