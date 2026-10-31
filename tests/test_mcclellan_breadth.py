import json
import unittest
from datetime import date, timedelta
from pathlib import Path

from core.breadth import _next_verified_trading_day, add_standard_mcclellan, attach_historical_mcl_reference


def example_rows(count=42):
    day = date(2026, 8, 25)
    rows = []
    for i in range(count):
        rows.append(dict(date=day.isoformat(), advance=600+i*3, decline=500,
                         expected=2000, covered=2000, missing=0, status='closed',
                         source='example', universe='沪深示例'))
        day = _next_verified_trading_day(day)
    return rows


class McClellanTests(unittest.TestCase):
    def test_standard_smoothing_and_warmup(self):
        rows = example_rows()
        result = add_standard_mcclellan(rows)
        fast = slow = 100.0
        for i in range(1, 39):
            fast = .10 * (100+i*3) + .90 * fast
            slow = .05 * (100+i*3) + .95 * slow
        self.assertTrue(all(r['mcl_standard'] is None for r in result[:38]))
        self.assertEqual(result[38]['mcl_samples'], 39)
        self.assertAlmostEqual(result[38]['mcl_standard'], fast-slow)
        self.assertNotIn('mcl_standard', rows[0])

    def test_gap_incomplete_and_changed_source_reset_the_run(self):
        rows = example_rows()
        for variant in ('gap', 'incomplete', 'provisional', 'source', 'universe'):
            changed = [r.copy() for r in rows]
            if variant == 'gap': changed.pop(10)
            elif variant == 'incomplete': changed[10]['missing'] = 1
            elif variant == 'provisional': changed[10]['status'] = 'provisional'
            elif variant == 'source': changed[10]['source'] = 'other'
            else: changed[10]['universe'] = 'other'
            out = add_standard_mcclellan(changed)
            self.assertIsNone(out[-1]['mcl_standard'], variant)
            self.assertLess(out[-1]['mcl_samples'], 39, variant)

    def test_holidays_and_unknown_calendar(self):
        self.assertEqual(_next_verified_trading_day(date(2026,9,24)), date(2026,9,28))
        self.assertEqual(_next_verified_trading_day(date(2026,9,30)), date(2026,10,8))
        self.assertIsNone(_next_verified_trading_day(date(2026,12,31)))
        row=example_rows(1)[0]
        row['date']='2026-10-01'
        self.assertIsNone(add_standard_mcclellan([row])[0]['mcl_standard'])
        self.assertEqual(add_standard_mcclellan([row])[0]['mcl_samples'],0)

    def test_verified_fixture_is_not_joined_across_data_sources(self):
        rows=json.loads(Path('public/breadth-preview.json').read_text())['days']
        out=add_standard_mcclellan(rows)
        historical=next(r for r in out if r['date']=='2026-10-26')
        live=next(r for r in out if r['date']=='2026-10-27')
        self.assertEqual(historical['mcl_samples'],99)
        self.assertIsNotNone(historical['mcl_standard'])
        self.assertIsNone(live['mcl_standard'])
        self.assertEqual(live['mcl_samples'],1)

    def test_same_day_reference_is_independent_and_retains_its_source(self):
        history=[{**r,'historical':True} for r in example_rows()]
        history[-1]['ma_breadth']={'date':history[-1]['date'],'source':'example','windows':{'20':{'percent':14.6}}}
        merged=[r.copy() for r in history]
        merged[-1]={**merged[-1],'historical':False,'source':'live-source','universe':'live-universe','advance':50}
        result=attach_historical_mcl_reference(add_standard_mcclellan(merged),history)
        self.assertIsNone(result[-1]['mcl_standard'])
        reference=result[-1]['mcl_history']
        self.assertEqual(reference['source'],'example')
        self.assertEqual(reference['universe'],'沪深示例')
        self.assertEqual(reference['samples'],42)
        self.assertAlmostEqual(reference['value'],add_standard_mcclellan(history)[-1]['mcl_standard'])
        self.assertEqual(result[-1]['ma_history']['date'],history[-1]['date'])
        self.assertEqual(result[-1]['ma_history']['source'],'example')
        self.assertNotIn('mcl_history',result[-2])
        stale=add_standard_mcclellan(merged)
        stale[-1]['mcl_history']={'value':999}
        stale[-1]['ma_history']={'date':'stale'}
        self.assertNotIn('mcl_history',attach_historical_mcl_reference(stale,history[:-1])[-1])
        self.assertNotIn('ma_history',attach_historical_mcl_reference(stale,history[:-1])[-1])

    def test_extended_history_remains_independent_when_live_close_overrides_one_day(self):
        history=json.loads(Path('fixtures/breadth-history-verified.json').read_text())
        mixed=[dict(r) for r in history]
        live=next(r for r in mixed if r['date']=='2026-10-27')
        live.update(historical=False,source='独立实时来源',universe='独立实时股票范围')
        result=attach_historical_mcl_reference(add_standard_mcclellan(mixed),history)
        row=next(r for r in result if r['date']=='2026-10-27')
        self.assertIsNone(row['mcl_standard'])
        self.assertEqual(row['mcl_samples'],1)
        self.assertEqual(row['mcl_history']['samples'],146)
        self.assertAlmostEqual(row['mcl_history']['value'],-279.05224989501255)
        self.assertNotEqual(row['source'],row['mcl_history']['source'])
        latest=next(r for r in mixed if r['date']=='2026-10-30')
        latest.update(historical=False,source='独立实时来源',universe='独立实时股票范围')
        result=attach_historical_mcl_reference(add_standard_mcclellan(mixed),history)
        row=next(r for r in result if r['date']=='2026-10-30')
        self.assertIsNone(row['mcl_standard'])
        self.assertEqual(row['mcl_history']['date'],'2026-10-30')
        self.assertEqual(row['mcl_history']['samples'],149)
        self.assertAlmostEqual(row['mcl_history']['value'],-343.06021548737954)
        self.assertNotEqual(row['source'],row['mcl_history']['source'])

    def test_historical_reference_survives_intervening_live_day(self):
        history=[{**r,'historical':True} for r in example_rows()]
        mixed=[dict(r) for r in history]
        mixed[-2].update(historical=False,source='live')
        joined=add_standard_mcclellan(mixed)
        self.assertIsNone(joined[-1]['mcl_standard'])
        result=attach_historical_mcl_reference(joined,history)
        self.assertEqual(result[-1]['mcl_history']['samples'],42)
        self.assertAlmostEqual(result[-1]['mcl_history']['value'],add_standard_mcclellan(history)[-1]['mcl_standard'])

    def test_provisional_date_does_not_inherit_later_close_reference(self):
        history=[{**r,'historical':True} for r in example_rows()]
        history[-1]['ma_breadth']={'date':history[-1]['date'],'source':'historical','windows':{}}
        merged=[r.copy() for r in history]
        merged[-1].update(historical=False,status='provisional',source='live')
        result=attach_historical_mcl_reference(add_standard_mcclellan(merged),history)
        self.assertNotIn('mcl_history',result[-1])
        self.assertNotIn('ma_history',result[-1])


if __name__ == '__main__':
    unittest.main()
