import json, tempfile, unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from core.app import App
from core.provider import CN

FIXTURE = Path(__file__).parent / 'fixtures' / 'ma250-pullback-603533.json'


def bars_until(stamp):
    bars = json.loads(FIXTURE.read_text(encoding='utf-8'))['bars']
    return bars[:next(index for index, bar in enumerate(bars) if bar['date'] == stamp) + 1]


class StrongAlertTest(unittest.TestCase):
    def setUp(self):
        self.calendar_patch=patch('core.app.annual_sessions',side_effect=lambda now,n:[now.date().isoformat()]);self.calendar_patch.start()
        self.tmp = tempfile.TemporaryDirectory()
        self.app = App(self.tmp.name, False)
        self.code = 'sh600000'
        self.day = '2025-08-18'
        self.bars = bars_until(self.day)
        for bar in self.bars:
            self.app.store.cache(self.code, 'daily', bar['date'],
                                 dict(bar, volume='0', volume_unit='shares', source='tencent', adjustment='none'))
        self.app.store.execute("INSERT OR REPLACE INTO watch(code,name) VALUES(?,?)", (self.code, '强信号样本'))
        self.app.store.execute("INSERT OR REPLACE INTO instruments(code,name) VALUES(?,?)", (self.code, '强信号样本'))
        self.now = datetime.fromisoformat(self.day + 'T15:25').replace(tzinfo=CN)
        self.app.market_regime.above_map = lambda: {self.day: True}

    def tearDown(self):
        self.calendar_patch.stop()
        self.app.store.db.close()
        self.tmp.cleanup()

    def events(self):
        return self.app.store.query("SELECT * FROM events WHERE json_extract(payload,'$.kind')='MA250_PULLBACK'")

    def test_strong_close_alert_is_created_once(self):
        self.app.check_ma250(self.code, self.now)
        rows = self.events()
        self.assertEqual(len(rows), 1)
        payload = json.loads(rows[0]['payload'])
        self.assertIn(self.code,payload['key'])
        self.assertIn(payload['rule_id'],payload['key'])
        self.assertIn(payload['episode_id'],payload['key'])
        self.assertIn('年线回踩强信号', payload['notification_title'])
        self.assertIn('强', payload['notification_body'])
        self.app.check_ma250(self.code, self.now)
        self.assertEqual(len(self.events()), 1)
        journal = [dict(data=json.loads(r['payload'])) for r in self.app.store.query("SELECT payload FROM ma250_journal WHERE code=? AND day=? AND phase='confirmed'",(self.code,self.day))]
        self.assertEqual(len(journal), 1)
        self.assertTrue(journal[0]['data']['signal']['strong'])
        self.assertTrue(journal[0]['data']['market_above'])

    def test_below_or_unknown_market_sends_nothing(self):
        self.app.market_regime.above_map = lambda: {self.day: False}
        self.app.check_ma250(self.code, self.now)
        self.assertEqual(self.events(), [])
        self.assertIs([dict(data=json.loads(r['payload'])) for r in self.app.store.query("SELECT payload FROM ma250_journal WHERE code=? AND day=? AND phase='confirmed'",(self.code,self.day))][0]['data']['market_above'], False)
        self.app.ma250_checked.clear()
        self.app.market_regime.above_map = lambda: {}
        self.app.check_ma250(self.code, self.now)
        self.assertEqual(self.events(), [])
        # Frozen known-market observation is not overwritten by a later outage.
        self.assertIs([dict(data=json.loads(r['payload'])) for r in self.app.store.query("SELECT payload FROM ma250_journal WHERE code=? AND day=? AND phase='confirmed'",(self.code,self.day))][0]['data']['market_above'],False)

    def test_switches_and_incomplete_bars_block_the_alert(self):
        partial = dict(self.app.store.getcache(self.code, 'daily', self.day)[0]['data'], provisional=True)
        self.app.store.cache(self.code, 'daily', self.day, partial)
        self.app.check_ma250(self.code, self.now)
        self.assertEqual(self.events(), [])
        self.app.store.cache(self.code, 'daily', self.day, self.bars[-1])
        self.app.store.setconfig('ma250_alert', False)
        self.app.check_ma250(self.code, self.now)
        self.assertEqual(self.events(), [])
        self.app.store.setconfig('ma250_alert', True)
        self.app.check_ma250(self.code, self.now)
        self.assertEqual(len(self.events()), 1)

    def test_no_alert_before_the_close_window(self):
        self.app.check_ma250(self.code, self.now.replace(hour=14, minute=50))
        self.assertEqual(self.events(), [])

    def test_v1_history_stays_visible_but_non_strong_signal_does_not_alert(self):
        code = 'sh603533'
        bars = bars_until('2026-11-02')
        for bar in bars:
            self.app.store.cache(code, 'daily', bar['date'],
                                 dict(bar, volume='0', volume_unit='shares', source='tencent', adjustment='none'))
        self.app.store.execute("INSERT OR REPLACE INTO watch(code,name) VALUES(?,?)", (code, '掌阅科技'))
        self.app.store.execute("INSERT OR REPLACE INTO instruments(code,name) VALUES(?,?)", (code, '掌阅科技'))
        view = self.app.call('history', dict(code=code, start='2024-11-01', end='2026-11-02'))
        self.assertEqual([item['date'] for item in view['ma250']['signals']],
                         ['2025-08-18', '2025-11-25', '2026-09-29', '2026-11-02'])
        self.assertEqual([signal['date'] for signal in view['ma250']['signals'] if signal['strong']], ['2025-08-18'])
        self.assertFalse(next(signal for signal in view['ma250']['signals'] if signal['date'] == '2026-11-02')['strong'])
        self.app.market_regime.above_map = lambda: {bar['date']: True for bar in bars}
        self.app.check_ma250(code, datetime(2026, 11, 2, 15, 25, tzinfo=CN))
        self.assertEqual(self.events(), [])
        journal = [dict(data=json.loads(r['payload'])) for r in self.app.store.query("SELECT payload FROM ma250_journal WHERE code=? AND day=? AND phase='confirmed'",(code,'2026-11-02'))]
        self.assertEqual(len(journal), 1)
        self.assertFalse(journal[0]['data']['signal']['strong'])


if __name__ == '__main__':
    unittest.main()