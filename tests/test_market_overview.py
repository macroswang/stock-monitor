import tempfile
import unittest
from pathlib import Path
from core.app import App


class MarketOverviewTests(unittest.TestCase):
    def test_overview_uses_index_quote_day_not_stock_chart_day(self):
        with tempfile.TemporaryDirectory() as directory:
            app=App(Path(directory),start_worker=False)
            try:
                app.store.cache('sh000001','market_quote','2026-10-30',dict(code='sh000001',timestamp='2026-10-30T15:00:00+08:00'))
                for day in ('2026-10-29','2026-10-30'):
                    app.store.cache('sh000001','market_minute',day,dict(date=day,bars=[]))
                self.assertEqual(app.call('market',{'day':'2026-10-29'})['minute']['date'],'2026-10-29')
                self.assertEqual(app.call('market_overview',{})['minute']['date'],'2026-10-30')
                self.assertIsNone(app.call('sector_flow',{'kind':'concept'})['snapshot'])
                self.assertIsNone(app.call('external_market',{})['snapshot'])
                with self.assertRaises(ValueError):app.call('sector_flow',{'kind':'invalid'})
            finally:
                app.stop.set()
                app.store.db.close()


if __name__=='__main__':unittest.main()
