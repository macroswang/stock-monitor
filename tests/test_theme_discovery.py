from datetime import datetime
import io
import json
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from unittest.mock import patch
from core import theme_discovery as d

class Discover(unittest.TestCase):
    def test_unseen_names_enter_without_editing_registry_and_expire(self):
        news=[{'title':'新型玻璃概念盘中走强'}]
        rows=[{'code':'600001','reason_type':'柔性车壳+季报扭亏+单股标签'},
              {'code':'600002','reason_type':'柔性车壳+普通行业'},
              {'code':'600003','reason_type':'普通行业'}]
        with patch.object(d.theme_sources,'expand',return_value=({},{},{})),patch.object(d,'observations',return_value=rows),patch.object(d,'bulletin_library',return_value=([],0)),patch.object(d,'trading_day',side_effect=lambda dt:dt.weekday()<5):
            pools,status=d.discover('2026-11-06',news,[{'name':'普通行业'}])
            labels=[v[0] for v in pools.values()]
            self.assertIn('柔性车壳',labels)
            self.assertIn('新型玻璃',labels)
            self.assertNotIn('单股标签',labels)
            self.assertNotIn('普通行业',labels)
            self.assertEqual(status['failed_days'],0)
            with patch.object(d,'observations',return_value=[]):
                new,_=d.discover('2026-11-16',[],[])
                self.assertNotIn('柔性车壳',[v[0] for v in new.values()])

    def test_news_and_market_tags_alone_do_not_establish_membership(self):
        def row(title,code):
            return ('sh'+code,'测试','2026-11-02',title,'https://example.org/a.pdf')
        rows=[row('关于签订<em>柔性</em>车壳项目合同的公告','600001'),
              row('关于终止柔性车壳项目合同的公告','600002'),
              row('关于签订柔性车壳项目合同的公告','600002'),
              row('关于签订柔性材料合同的公告','600003')]
        result,_=d.filing_matches('柔性车壳',rows)
        self.assertEqual([r[0] for r in result],['sh600001'])

    def test_new_membership_survives_restart_and_live_check_uses_saved_issue(self):
        from core import daily_outlook
        from core.provider import CN
        now=datetime(2026,11,6,11,0,tzinfo=CN)
        codes=['sh600001','sz300002','sz300003','sz300004']
        members=[dict(code=c,name=c,basis='订单',source='https://example.org/one.pdf') for c in codes]
        theme=dict(code='topic_never_seen',name='新业务',members=members)
        issue=dict(published_at=now.isoformat(),ideas=[dict(sector_code=theme['code'],stocks=members[:3],core_members=members)],themes=[theme])
        with TemporaryDirectory() as folder,patch.object(daily_outlook,'now_cn',return_value=now):
            root=Path(folder);(root/'daily-outlook').mkdir()
            (root/'daily-outlook/2026-11-06_1030.json').write_text(json.dumps(issue))
            records=[dict(data=dict(date='2026-11-06',collected_at='batch',quotes=members))]
            flow=Mock();flow.view.return_value={theme['code']:{'net':1}}
            app=SimpleNamespace(dir=root,store=Mock(),live_theme_flow=flow,sector_flow=Mock())
            app.store.getcache.return_value=records
            app.sector_flow.view.return_value={}
            report=daily_outlook.view(app,'2026-11-06','batch')
            self.assertEqual({q['code'] for q in report['quotes']},set(codes))
            self.assertIn(theme['code'],report['sectors'])
            self.assertEqual(set(flow.view.call_args.args[-1]),set(codes))

    def test_investor_question_cannot_supply_business_evidence(self):
        from core import theme_sources as src
        from core.provider import CN
        now=datetime(2026,11,7,12,tzinfo=CN)
        def item(code,reply,stamp):
            return dict(stockCode=code,contentType=11,mainContent='请问公司是否量产光模块？',
                        attachedContent=reply,attachedPubDate=stamp,companyShortName='甲',indexId=code)
        ts=int(now.timestamp()*1000)
        replies=[item('300001','公司已量产光模块。',ts),item('300002','感谢您的关注。',ts),
                 item('300003','公司不涉及光模块业务。',ts),item('300003','公司已量产光模块。',ts-1000),
                 item('300004','公司已量产光模块。',ts+1000)]
        with patch.object(src,'read_json',return_value={'results':replies}):
            found,veto=src.answers('光模块',now)
        self.assertEqual(set(found),{'sz300001'})
        self.assertIn('sz300003',veto)

    def test_annual_evidence_requires_a_business_link_and_avoids_name_collision(self):
        from core.theme_sources import topic_pattern,positive_links
        text='公司生产高速交换机。公司运营高速公路。公司暂无光模块相关业务。公司销售工业传感器。'
        self.assertEqual([key for key,_ in positive_links(text,topic_pattern(['高速','光模块','工业传感器']))],['高速','工业传感器'])
