import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.app import App


class TradingChartSyncGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.app=App(Path(self.tmp.name),start_worker=False);self.addCleanup(self.app.store.db.close)

    def test_live_market_sync_is_rejected_before_a_broker_job_can_compete_with_orders(self):
        self.app.store.setconfig('trading_mode','live');self.app.store.setconfig('trading_paused',False)
        with patch('core.app.trading',return_value=True),patch.object(self.app,'broker_job',side_effect=AssertionError('must not start')):
            with self.assertRaisesRegex(ValueError,'优先保障|\u5360用下单设备'):
                self.app.call('trading_chart_sync',{'day':'2026-11-06'})

    def test_paused_or_closed_market_can_start_read_only_sync(self):
        self.app.store.setconfig('trading_mode','live');self.app.store.setconfig('trading_paused',True)
        with patch('core.app.trading',return_value=True),patch.object(self.app,'broker_job',return_value={'job':'safe'}) as start:
            self.assertEqual(self.app.call('trading_chart_sync',{'day':'2026-11-06'}),{'job':'safe'})
        start.assert_called_once()
