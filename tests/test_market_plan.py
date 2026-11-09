import unittest
from unittest.mock import patch

from core import market_plan as plan

DAY = '2026-11-06'
STAMP = DAY + 'T10:30:00+08:00'


def quote(code, price, previous, low, amount, day=DAY):
    return dict(code=code, price=str(price), previous_close=str(previous), day_low=str(low),
                amount_yuan=str(amount), timestamp=day + 'T10:30:00+08:00')


def member(code, name, price, previous, low, amount, day=DAY):
    return dict(code=code, name=name, price=str(price), previous_close=str(previous),
                day_low=str(low), amount_yuan=str(amount), timestamp=day + 'T10:30:00+08:00')


def idea(sector='电力行业', code='new_dlhy', kind='行业', change=2.0, net=3e8, members=None,
         stocks=None, news_title=None, risk='若板块资金转为流出，继续等。'):
    members = members or [('sh600001', '甲'), ('sh600002', '乙'), ('sh600003', '丙'), ('sh600004', '丁')]
    stocks = stocks or [dict(code=members[0][0], name=members[0][1], low=9.8),
                        dict(code=members[1][0], name=members[1][1], low=9.8),
                        dict(code=members[2][0], name=members[2][1], low=9.8)]
    return dict(sector=sector, sector_code=code, sector_kind=kind, change=change, net=net,
                members=[dict(code=c, name=n) for c, n in members],
                core_members=[dict(code=c, name=n) for c, n in members], stocks=stocks,
                news_title=news_title, risk=risk, allow_entry=True)


def breadth(advance=3000, decline=2000, flat=100):
    active = advance + decline + flat
    return dict(date=DAY, status='closed', advance=advance, decline=decline, flat=flat, active=active,
                advancing_percent=round(100 * advance / active, 2), trin=1.0, trin_volume=1.0,
                amount_yuan=1.6e12, amount_5d_avg=1.7e12, amount_ratio=0.94, days_used=5)


def indices(above=True):
    row = dict(code='sh000001', name='上证指数', price=3700.0, percent=1.0,
               ma5=3650.0 if above else 3750.0, ma10=3600.0 if above else 3800.0,
               ma20=3550.0 if above else 3900.0, above_ma5=above, above_ma20=above,
               high20=3800.0, low20=3500.0, volume=1e8, volume_ratio=1.0,
               support=3550.0, resistance=3800.0, stamp=STAMP)
    return [row, dict(row, code='sz399001', name='深证成指'), dict(row, code='sz399006', name='创业板指')]


def sentiment(limit_up=50, yesterday=40, down=5, sealed=.72, max_board=3, by_code=None, temperature='分化'):
    return dict(limit_up=dict(today=limit_up, yesterday=yesterday, attempt=int(limit_up / sealed),
                              open_num=int(limit_up / sealed) - limit_up, sealed_rate=sealed),
                limit_down=dict(today=down, yesterday=0, attempt=down, sealed_rate=None),
                max_board=max_board, max_board_name='某某', ladder=[], non_consecutive=0,
                yesterday_performance=None, hot_reasons=[], trend=[], temperature=temperature,
                by_code=by_code or {})


def pulse(breadth_row=None, index_rows=None, senti=None, capital_by_code=None, persistent=None):
    return dict(market=dict(indices=index_rows or indices(), breadth=breadth_row or breadth(), signals=[]),
                capital=dict(industry=dict(label='行业', measure='买卖方向净额', date=DAY, source='新浪行业资金流',
                                           quote_time=None, date_inferred=True, inflow=[], outflow=[]),
                             concept=dict(label='概念', measure='买卖方向净额', date=DAY, source='新浪概念资金流',
                                          quote_time=None, date_inferred=True, inflow=[], outflow=[]),
                             persistent=persistent or [], history_days=5, by_code=capital_by_code or {}),
                sentiment=senti if senti is not None else sentiment(),
                hotspots=dict(news=[], reasons=[]), warnings=[])


SUMMARY = dict(date=DAY, status='closed', covered=5223)


class Stats(unittest.TestCase):
    def test_quote_stats_rejects_stale_and_inconsistent(self):
        stats = plan.quote_stats({'sh600001': quote('sh600001', 10.2, 10, 9.8, 1e8),
                                  'sh600002': quote('sh600002', 10.2, 10, 9.8, 1e8, '2026-11-05'),
                                  'sh600003': quote('sh600003', 10.0, 10, 10.2, 1e8)}, DAY)
        self.assertEqual(list(stats), ['sh600001'])
        self.assertAlmostEqual(stats['sh600001']['pct'], 2.0)


class Scoring(unittest.TestCase):
    def test_parts_are_explicit_and_add_up(self):
        members = [('sh600001', '甲'), ('sh600002', '乙'), ('sh600003', '丙')]
        quotes = {code: quote(code, 10.2, 10, 9.9, 1e8) for code, _ in members}
        stats = plan.quote_stats(quotes, DAY)
        pool = {'sh600001': dict(boards=2, days=2), 'sh600002': dict(boards=1, days=1)}
        capital = {'new_dlhy': dict(net_5d=8e8, days=5, source='新浪行业资金流', measure='买卖方向净额')}
        scored = plan.score_direction(idea(news_title='电力保供需求回升', members=members), stats, pool, capital)
        self.assertEqual(scored['parts'], dict(capital=2.5, trend=2.5, sentiment=1.5, hotspot=0.7, evidence=0))
        self.assertEqual(scored['score'], 7.2)
        self.assertEqual(scored['boards'], 2)
        self.assertEqual((scored['rising'], scored['checked']), (3, 3))

    def test_caution_headline_and_missing_history(self):
        members = [('sh600001', '甲'), ('sh600002', '乙')]
        stats = plan.quote_stats({code: quote(code, 10.2, 10, 9.9, 1e8) for code, _ in members}, DAY)
        stock = idea(news_title='出口限制担忧升温', net=-1e8, members=members,
                     stocks=[dict(code=members[0][0], name=members[0][1], low=9.8),
                             dict(code=members[1][0], name=members[1][1], low=9.8)])
        scored = plan.score_direction(stock, stats, {}, {})
        self.assertEqual(scored['parts']['hotspot'], -0.5)
        self.assertEqual(scored['parts']['capital'], 0)
        self.assertIsNone(scored['net_5d'])


class Roles(unittest.TestCase):
    def test_roles_use_boards_amount_and_are_deduped(self):
        members = [('sh600001', '候选'), ('sh600002', '龙头'), ('sh600003', '中军'),
                   ('sh600004', '弹性'), ('sh600005', 'ST样本')]
        stock = idea(members=members)
        quotes = {'sh600001': quote('sh600001', 10.1, 10, 9.9, 1e8),
                  'sh600002': quote('sh600002', 11.0, 10, 9.9, 2e8),
                  'sh600003': quote('sh600003', 10.3, 10, 9.9, 8e8),
                  'sh600004': quote('sh600004', 10.2, 10, 9.9, 1e8),
                  'sh600005': quote('sh600005', 10.2, 10, 9.9, 5e8)}
        pool = {'sh600002': dict(boards=3, days=3, name='龙头', reason='电力+设备', order_amount=2e8)}
        levels = {code: dict(ma5=9.9, ma10=9.6, ma20=9.2, high20=11.0, low20=8.8) for code in quotes}
        stocks = plan.pick_stocks(stock, quotes, pool, levels, DAY, True)
        self.assertEqual([row['role'] for row in stocks], ['低吸候选', '龙头', '中军', '弹性'])
        self.assertEqual([row['name'] for row in stocks], ['候选', '龙头', '中军', '弹性'])
        self.assertEqual(stocks[1]['boards'], 3)
        self.assertEqual(stocks[1]['limit_tag'], '涨停')
        self.assertEqual(stocks[0]['name'], '候选')
        self.assertTrue(all(row['entry']['stop'] for row in stocks))


class Entry(unittest.TestCase):
    def test_entry_numbers_follow_the_contract(self):
        stats = dict(price=10.2, previous=10.0, low=9.8, amount=1e8, pct=2.0)
        levels = dict(ma5=9.9, ma10=9.5, ma20=9.0, high20=11.0, low20=8.0)
        entry = plan.stock_entry(stats, levels, '低吸候选')
        self.assertEqual((entry['buy_low'], entry['buy_high'], entry['chase']), (9.9, 10.2, 10.3))
        self.assertAlmostEqual(entry['stop'], 9.31)
        # Buy and sell points both exist and are ordered around the current price.
        self.assertEqual(entry['target1'], 11.0)
        self.assertGreaterEqual(entry['target2'], 11.5)
        self.assertEqual(entry['trail'], 9.9)
        self.assertIn('分批减半', entry['sell_note'])
        self.assertIn('1–3 个交易日', entry['sell_note'])
        leader = plan.stock_entry(stats, levels, '龙头')
        self.assertEqual((leader['buy_high'], leader['chase']), (10.2, 10.7))
        self.assertTrue(entry['buy_low'] < entry['buy_high'] < entry['target1'])
        self.assertTrue(entry['stop'] < entry['buy_low'])

    def test_strong_name_stop_is_capped_near_intraday_low(self):
        stats = dict(price=20.0, previous=18.0, low=18.0, amount=1e8, pct=11.1)
        levels = dict(ma5=17.0, ma10=10.0, ma20=8.0, high20=20.0, low20=5.0)
        entry = plan.stock_entry(stats, levels, '龙头')
        self.assertAlmostEqual(entry['stop'], round(max(10.0, 18.0 * .93) * .98, 2))


class Assess(unittest.TestCase):
    def direction(self, change=2.0, net=3e8, closed=True):
        return dict(candidate=dict(code='sh600001'), peers=[dict(code='sh600002'), dict(code='sh600003')],
                    entry_stop=9.3, peer_stops={'sh600002': 9.4, 'sh600003': 9.4},
                    change=change, net=net, closed=closed, news_title=None)

    def quotes(self, candidate_price=10.2, candidate_low=9.8, peer_price=10.1, peer_low=9.9):
        return {'sh600001': quote('sh600001', candidate_price, 10, candidate_low, 1e8),
                'sh600002': quote('sh600002', peer_price, 10, peer_low, 1e8),
                'sh600003': quote('sh600003', peer_price, 10, peer_low, 1e8)}

    def test_ready_is_downgraded_after_close(self):
        result = plan.assess(self.direction(), self.quotes(), DAY, breadth())
        self.assertEqual(result['status'], 'watch')
        self.assertIn('收盘', result['why'])
        self.assertEqual(plan.assess(self.direction(closed=False), self.quotes(), DAY, breadth())['status'], 'ready')

    def test_gates_one_by_one(self):
        self.assertEqual(plan.assess(self.direction(), self.quotes(), DAY, breadth(advance=500, decline=4500))['status'], 'watch')
        self.assertEqual(plan.assess(self.direction(change=-1), self.quotes(), DAY, breadth())['status'], 'watch')
        self.assertEqual(plan.assess(self.direction(), self.quotes(candidate_price=10.6), DAY, breadth())['status'], 'watch')
        self.assertEqual(plan.assess(self.direction(), self.quotes(candidate_price=9.2, candidate_low=9.0), DAY, breadth())['status'], 'weak')
        self.assertEqual(plan.assess(self.direction(), self.quotes(peer_price=9.2, peer_low=9.0), DAY, breadth())['status'], 'weak')
        self.assertEqual(plan.assess(self.direction(), {}, DAY, breadth())['status'], 'missing')

    def test_state_avoid_on_caution_news(self):
        direction = self.direction(closed=False)
        result = plan.assess(direction, self.quotes(), DAY, breadth(advance=500, decline=4500))
        direction['news_title'] = '出口限制升级'
        state, why = plan.state_of(result, direction, None)
        self.assertEqual(state, '回避')
        self.assertIn('消息面', why)
        direction['news_title'] = None
        state, why = plan.state_of(result, direction, None)
        self.assertEqual(state, '继续等')


class Regime(unittest.TestCase):
    def test_strong_attack(self):
        strong = pulse()
        strong['market']['indices'] = indices(True)
        strong['market']['breadth'] = breadth(advance=4000, decline=1100)
        strong['market']['breadth'].update(amount_ratio=1.2, advancing_percent=79.0)
        state = plan.regime(strong, SUMMARY)
        self.assertEqual((state['bias'], state['verdict']), ('进攻', '普涨修复 · 可跟随强势'))
        self.assertIn('5–6', state['position'])

    def test_weak_is_defensive(self):
        weak = pulse()
        weak['market']['indices'] = indices(False)
        weak['market']['breadth'] = breadth(advance=700, decline=4400)
        weak['market']['breadth'].update(amount_ratio=0.8, advancing_percent=13.7)
        weak['sentiment'] = sentiment(limit_up=20, yesterday=40, down=15, sealed=.65, max_board=5, temperature='退潮')
        state = plan.regime(weak, SUMMARY)
        self.assertEqual((state['bias'], state['verdict']), ('防守', '情绪退潮 · 防守为主'))
        self.assertIn('≤2', state['position'])

    def test_missing_market_is_explicit(self):
        state = plan.regime(dict(market=None, sentiment=None), SUMMARY)
        self.assertEqual(state['bias'], '防守')
        self.assertIn('数据不足', state['verdict'])

class Timetable(unittest.TestCase):
    def test_every_rule_line_has_a_number_or_dash(self):
        state = dict(bias='试错', verdict='分化震荡 · 精选方向', position='总仓 3–4 成，单方向 ≤1.5 成。', indices=[])
        senti = sentiment(limit_up=40, yesterday=30, down=5, sealed=.65)
        senti['limit_up']['open_num'] = 13
        rows = plan.timetable(pulse(senti=senti), state, [])
        self.assertEqual([row['time'] for row in rows], ['9:15–9:25', '9:30–10:00', '10:30', '14:30', '收盘后'])
        close = next(row for row in rows if row['time'] == '14:30')
        self.assertIn('0.90 倍', close['rule'])
        self.assertIn('0.60', close['rule'])
        self.assertIn('≥15 家', close['rule'])
        self.assertIn('0.65', close['rule'])
        self.assertIn('13', close['rule'])


class Build(unittest.TestCase):
    def test_report_is_ordered_and_complete(self):
        members_a = [('sh600001', '甲'), ('sh600002', '乙'), ('sh600003', '丙')]
        members_b = [('sh600011', '戊'), ('sh600012', '己'), ('sh600013', '庚')]
        quotes = {code: quote(code, 10.2, 10, 9.9, 1e8) for code, _ in members_a + members_b}
        quotes['sh600001'] = quote('sh600001', 10.1, 10, 9.9, 2e8)
        first = idea(members=members_a, change=3.0, net=5e8)
        second = idea(sector='商业百货', code='new_sybh', members=members_b, change=1.0, net=1e8)
        pool = {'sh600002': dict(boards=3, days=3, name='乙'), 'sh600011': dict(boards=1, days=1, name='戊')}
        senti = sentiment(by_code=pool)
        capital = {'new_dlhy': dict(net_5d=8e8, days=5, source='新浪行业资金流', measure='买卖方向净额')}
        state = pulse(senti=senti, capital_by_code=capital)
        dates = plan.market_pulse.recent_trading_days(DAY, 25)
        bars = {code: [dict(date=date, open=10, close=10, high=10.2, low=9.8, volume=1000) for date in dates]
                for code in quotes}
        with patch.object(plan.market_pulse, 'stock_daily', return_value=(bars, [])):
            result = plan.build(None, [second, first], state, quotes, dict(SUMMARY, status='provisional'))
        self.assertEqual(result['directions'][0]['sector'], '电力行业')
        self.assertEqual([row['rank'] for row in result['directions']], [1, 2])
        for key in ('rank', 'sector', 'sector_code', 'sector_kind', 'change', 'net', 'net_5d', 'score',
                    'score_parts', 'state', 'why', 'opportunity', 'logic', 'risk', 'candidate', 'peers',
                    'stocks', 'timing', 'evidence'):
            self.assertIn(key, result['directions'][0])
        self.assertEqual(result['directions'][0]['stocks'][0]['role'], '低吸候选')
        self.assertTrue(result['directions'][0]['timing']['gates'])
        self.assertEqual(len(result['playbooks']), 3)
        self.assertTrue(any(item['active'] for item in result['playbooks']))
        self.assertIn('未来 1–3 个交易日', result['horizon'])
        self.assertTrue(result['timetable'])
        self.assertTrue(result['risk'])
        self.assertEqual(result['focus']['sector'], '电力行业')
        picks = result['top_picks']
        self.assertTrue(1 <= len(picks) <= 6)
        self.assertEqual(picks[0]['sector'], '电力行业')
        self.assertEqual(picks[0]['role'], '低吸候选')
        for pick in picks:
            self.assertTrue(pick['code'] and pick['name'])
            self.assertLess(pick['stop'], pick['buy_low'])
            self.assertLessEqual(pick['buy_low'], pick['buy_high'])
            self.assertGreater(pick['target1'], pick['buy_high'])
            self.assertIn('成', pick['sizing'])
            self.assertIn('9:45', pick['window'])
            self.assertIn('候选涨幅<5%', pick['trigger'])
        self.assertEqual(len({pick['code'] for pick in picks}), len(picks))

    def test_level_failure_degrades_to_quote_levels(self):
        members = [('sh600001', '甲'), ('sh600002', '乙'), ('sh600003', '丙')]
        quotes = {code: quote(code, 10.2, 10, 9.9, 1e8) for code, _ in members}
        with patch.object(plan.market_pulse, 'stock_daily', return_value=({}, [code for code, _ in members])):
            result = plan.build(None, [idea(members=members)], pulse(), quotes, SUMMARY)
        self.assertTrue(any('日线未取得' in warning for warning in result['warnings']))
        self.assertIsNone(result['directions'][0]['stocks'][0]['levels'])
        self.assertTrue(result['directions'][0]['stocks'][0]['entry']['note'])


if __name__ == '__main__':
    unittest.main()
