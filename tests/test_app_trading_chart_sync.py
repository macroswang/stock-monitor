import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.app import App


class TradingChartManualSyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.app=App(Path(self.tmp.name),start_worker=False);self.addCleanup(self.app.store.db.close)

    def test_user_can_sync_during_live_automatic_execution(self):
        self.app.store.setconfig('trading_mode','live');self.app.store.setconfig('trading_paused',False)
        with patch('core.app.trading',return_value=True),patch('core.trading_chart.sync_filled_orders',return_value={'saved':2}) as sync,patch.object(self.app,'broker_job',side_effect=lambda fn:fn()):
            self.assertEqual(self.app.call('trading_chart_sync',{'day':'2026-11-12'}),{'saved':2})
        sync.assert_called_once_with(self.app.store,'2026-11-12')

    def test_paused_or_closed_market_can_start_read_only_sync(self):
        self.app.store.setconfig('trading_mode','live');self.app.store.setconfig('trading_paused',True)
        with patch('core.app.trading',return_value=True),patch.object(self.app,'broker_job',return_value={'job':'safe'}) as start:
            self.assertEqual(self.app.call('trading_chart_sync',{'day':'2026-11-06'}),{'job':'safe'})
        start.assert_called_once()
