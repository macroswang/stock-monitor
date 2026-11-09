import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from core import outlook_scheduler as out
from core.provider import CN


class NativeSchedule(unittest.TestCase):
    def test_schedule_uses_china_clock_and_catches_up_latest_slot_only(self):
        self.assertEqual(out.due_slot(datetime(2026,11,7,0,29,tzinfo=timezone.utc)),'2026-11-07 08:00')
        self.assertEqual(out.due_slot(datetime(2026,11,7,0,30,tzinfo=timezone.utc)),'2026-11-07 08:30')
        self.assertEqual(out.due_slot(datetime(2026,11,7,16,0,tzinfo=timezone.utc)),'2026-11-08 00:00')
        with tempfile.TemporaryDirectory() as directory:
            app=SimpleNamespace(dir=Path(directory),store=None)
            worker=out.OutlookScheduler(app)
            now=[datetime(2026,11,7,9,45,tzinfo=CN)]
            factory=Mock(side_effect=[OSError('offline'),{'ideas':[]},{'ideas':[]}])
            def tick(w):w.tick(lambda:now[0],factory)
            tick(worker)
            self.assertIsNone(worker.done)
            self.assertFalse(list(app.dir.rglob('*.json')))
            tick(worker);tick(worker)
            restart=out.OutlookScheduler(app);tick(restart)
            self.assertEqual(factory.call_count,2)
            now[0]=now[0].replace(hour=20);tick(restart)
            slots=[json.loads(p.read_text())['native_slot'] for p in sorted(app.dir.rglob('*.json'))]
            self.assertEqual(slots,['2026-11-07 09:30','2026-11-07 20:30'])

    def test_multiple_distinct_sectors_actual_peers_and_news_failure(self):
        now=datetime(2026,11,7,20,0,tzinfo=CN)
        groups={s:[('sh6'+f'{i*10+j:05d}',f'公司{i}{j}') for j in range(3)]
                for i,s in enumerate(('new_a','gn_b'))}
        quotes={c:dict(day_low='9.99',previous_close='10',price='10.2',amount_yuan=str(99_000_000-j))
                for g in groups.values() for j,(c,_) in enumerate(g)}
        def flow(t,kind):
            s,n=('new_a','电力行业') if kind=='industry' else ('gn_b','水产品')
            return dict(date='2026-11-06',sectors=[dict(code=s,name=n,change_percent=1.2,net_yuan=1e8)])
        def feed(region,lid,t):return [dict(region=region,time=now.isoformat(),title='电力保供需求回升' if region=='domestic' else '国际资讯')]
        with patch.object(out.theme_discovery,'discover',return_value=({},{'filing_errors':{}})),patch.object(out,'market',return_value=({'date':'2026-11-06','covered':6},quotes)),patch.object(out.sector_flow,'fetch',side_effect=flow),patch.object(out,'members',side_effect=groups.get),patch.object(out,'news',side_effect=feed) as getnews,patch.object(out.market_pulse,'build',return_value={'warnings':[]}),patch.object(out.market_plan,'build',return_value={}):
            issue=out.produce(None,now)
            self.assertEqual(len(issue['ideas']),2)
            for i in issue['ideas']:
                self.assertEqual({s['code'] for s in i['stocks']},{s[0] for s in groups[i['sector_code']]})
            getnews.side_effect=OSError('offline')
            with self.assertRaises(OSError):out.produce(None,now)

    def test_peer_failure_preserves_actual_selected_stock_and_comparisons(self):
        members=[('sh600001','甲'),('sh600002','乙'),('sh600003','丙'),('sh600004','丁')]
        quotes={code:dict(day_low='9.5',previous_close='10',price=str(price),amount_yuan=amount)
                for (code,_),price,amount in zip(members,[10.2,9.9,10,10.3],[9e8,8e8,7e8,6e8])}
        selected,reason=out.select_stocks(members,quotes,set())
        self.assertIsNone(selected)
        self.assertIn('甲涨 2.00%',reason)
        self.assertIn('乙 -1.00%、丙 +0.00%',reason)
        quotes['sh600002']['price']='10.1'
        self.assertIsNotNone(out.select_stocks(members,quotes,set())[0])

    def test_disclosed_theme_can_outrank_industry_and_incomplete_pool_is_explained(self):
        from core import disclosure_themes as dt
        day='2026-11-06'
        now=datetime(2026,11,6,10,15,tzinfo=CN)
        stamp=now.isoformat()
        primary='topic_new'
        members=[(c,n,'已获订单','https://example.org/a.pdf') for c,n in
                 [('sz300001','新甲'),('sz300002','新乙'),('sz300003','新丙')]]
        registry={primary:('新出现的产业',members),'topic_other':('对比方向',members+[('sz300004','新丁','新订单','https://example.org/b.pdf')])}
        quotes={m[0]:dict(code=m[0],price='10.3',previous_close='10',day_low='9.99',amount_yuan=1e9,
                          timestamp=stamp) for m in members}
        ordinary=[('sh600001','甲'),('sh600002','乙'),('sh600003','丙')]
        for code,_ in ordinary:quotes[code]=dict(quotes[next(iter(quotes))],code=code)
        industry=dict(code='new_test',name='测试行业',net_yuan=1e8,change_percent=0.5)
        fetch_members=out.members
        def membership(code):
            return ordinary if code=='new_test' else fetch_members(code)
        with patch.object(out.theme_discovery,'discover',return_value=(registry,{'filing_errors':{}})),patch.object(dt,'money_flow',return_value=(1e7,stamp)), \
             patch.object(out,'market',return_value=({'date':day,'covered':7,'status':'provisional'},quotes)), \
             patch.object(out.sector_flow,'fetch',side_effect=lambda t,k:dict(date=day,sectors=[industry] if k=='industry' else [])), \
             patch.object(out,'members',side_effect=membership),patch.object(out,'news',return_value=[]),              patch.object(out.market_pulse,'build',return_value={'warnings':[]}),              patch.object(out.market_plan,'build',return_value={}):
            result=out.produce(None,now)
        idea=result['ideas'][0]
        self.assertEqual([i['sector_code'] for i in result['ideas']],[primary,'new_test'])
        self.assertTrue(idea['allow_entry'])
        self.assertEqual(len({s['code'] for s in idea['stocks']}),3)
        self.assertIn('未核对',result['exclusions']['topic_other'])

    def test_enriched_report_is_attached_and_degrades_on_failure(self):
        now=datetime(2026,11,7,20,0,tzinfo=CN)
        groups={'new_a':[('sh600001','甲'),('sh600002','乙'),('sh600003','丙')]}
        quotes={c:dict(day_low='9.99',previous_close='10',price='10.2',amount_yuan=str(99_000_000-j))
                for j,(c,_) in enumerate(groups['new_a'])}
        def flow(t,kind):
            return dict(date='2026-11-06',sectors=[dict(code='new_a',name='电力行业',change_percent=1.2,net_yuan=1e8)] if kind=='industry' else [])
        def feed(region,lid,t):return [dict(region=region,time=now.isoformat(),title='电力保供需求回升')]
        pulse={'market':None,'capital':None,'sentiment':None,'hotspots':None,'warnings':['人气数据未取得：涨停池']}
        report={'verdict':'分化震荡 · 精选方向','bias':'试错','position':'总仓 3–4 成，单方向 ≤1.5 成。','horizon':'未来 1–3 个交易日',
                'directions':[],'playbooks':[],'timetable':[],'risk':['不构成投资建议。'],'warnings':['候选股日线未取得。']}
        with patch.object(out.theme_discovery,'discover',return_value=({},{'filing_errors':{}})),patch.object(out,'market',return_value=({'date':'2026-11-06','covered':6},quotes)),patch.object(out.sector_flow,'fetch',side_effect=flow),patch.object(out,'members',side_effect=groups.get),patch.object(out,'news',side_effect=feed),patch.object(out.market_pulse,'build',return_value=pulse),patch.object(out.market_plan,'build',return_value=report),patch.object(out.market_radar,'build',return_value={'items':[],'summary':'','warnings':[]}):
            issue=out.produce(None,now)
        self.assertEqual(issue['bias'],'试错')
        self.assertEqual(issue['pulse'],pulse)
        self.assertEqual(issue['warnings'],['人气数据未取得：涨停池','候选股日线未取得。'])
        with patch.object(out.theme_discovery,'discover',return_value=({},{'filing_errors':{}})),patch.object(out,'market',return_value=({'date':'2026-11-06','covered':6},quotes)),patch.object(out.sector_flow,'fetch',side_effect=flow),patch.object(out,'members',side_effect=groups.get),patch.object(out,'news',side_effect=feed),patch.object(out.market_pulse,'build',side_effect=ValueError('涨停池未取得')),patch.object(out.market_plan,'build') as planner,patch.object(out.market_radar,'build'):
            issue=out.produce(None,now)
        self.assertIsNone(issue['pulse'])
        self.assertEqual(issue['bias'],'防守')
        self.assertEqual(issue['directions'],[])
        self.assertTrue(any('研判增强暂不可用' in w for w in issue['warnings']))
        planner.assert_not_called()

    def test_daily_outlook_view_keeps_the_enriched_report(self):
        from core import daily_outlook
        now=datetime(2026,11,6,20,0,tzinfo=CN)
        codes=['sh600001','sz300002','sz300003']
        members=[dict(code=c,name=c,basis='订单',source='https://example.org/a.pdf') for c in codes]
        theme=dict(code='topic_x',name='新业务',members=members)
        issue=dict(published_at=now.isoformat(),ideas=[dict(sector_code=theme['code'],stocks=members,core_members=members)],
                   themes=[theme],pulse=dict(market=None,capital=None,sentiment=None,hotspots=None,warnings=[]),
                   verdict='分化震荡 · 精选方向',bias='试错',directions=[dict(rank=1,sector='新业务',sector_code='topic_x',stocks=members)])
        with tempfile.TemporaryDirectory() as folder,patch.object(daily_outlook,'now_cn',return_value=now):
            root=Path(folder);(root/'daily-outlook').mkdir()
            (root/'daily-outlook/2026-11-06_2000.json').write_text(json.dumps(issue))
            records=[dict(data=dict(date='2026-11-06',collected_at='batch',quotes=members))]
            flow=Mock();flow.view.return_value={'topic_x':{'net':1}}
            app=SimpleNamespace(dir=root,store=Mock(),live_theme_flow=flow,sector_flow=Mock())
            app.store.getcache.return_value=records
            app.sector_flow.view.return_value={}
            report=daily_outlook.view(app,'2026-11-06','batch')
        self.assertEqual(report['issue']['bias'],'试错')
        self.assertEqual(report['issue']['directions'][0]['sector'],'新业务')
        self.assertEqual({q['code'] for q in report['quotes']},set(codes))
        self.assertIn('topic_x',report['sectors'])

    def test_intraday_flow_does_not_use_future_or_stale_minute(self):
        from core import disclosure_themes as dt
        quote=dict(price='10.10',previous_close='10',timestamp='2026-11-06T10:15:30+08:00')
        data={'data':dict(code='300182',market=0,klines=['2026-11-06 10:15,250','2026-11-06 10:16,450'])}
        with patch.object(dt,'get',return_value=json.dumps(data)):
            self.assertEqual(dt.money_flow('sz300182','捷成股份',quote,'2026-11-06',False)[0],250)
            quote['timestamp']='2026-11-06T10:20:00+08:00'
            with self.assertRaises(ValueError):dt.money_flow('sz300182','捷成股份',quote,'2026-11-06',False)
