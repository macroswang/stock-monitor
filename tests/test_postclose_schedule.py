import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from core.app import App, postclose_check_wait
from core.option_pcr import NOT_PUBLISHED
from core.provider import CN


class Clock:
    def __init__(self):
        self.now = datetime(2026, 10, 30, 16, 20, tzinfo=CN)
        self.waits = []

    def is_set(self):
        return len(self.waits) >= 3

    def wait(self, seconds):
        self.waits.append(seconds)
        self.now += timedelta(seconds=seconds)


class Service:
    def __init__(self, code=''):
        self.security_code = code
        self.error = ''
        self.calls = []

    def refresh(self, now):
        self.calls.append(now)


class PostcloseScheduleTests(unittest.TestCase):
    def test_wake_at_trading_day_boundary_and_preserve_weekend_retry(self):
        self.assertEqual(postclose_check_wait(datetime(2026, 10, 30, 16, 20, tzinfo=CN)), 600)
        self.assertEqual(postclose_check_wait(datetime(2026, 10, 30, 15, 0, tzinfo=CN)), 3600)
        self.assertEqual(postclose_check_wait(datetime(2026, 10, 31, 16, 20, tzinfo=CN)), 3600)
        self.assertEqual(postclose_check_wait(datetime(2026, 10, 30, 16, 31, tzinfo=CN), datetime(2026, 10, 30, 16, 29, tzinfo=CN)), 1)

    def test_each_loop_collects_new_session_once_at_boundary(self):
        for name, attrs in [('option_pcr_loop', ['option_pcr', 'option_pcr_300']),
                            ('etf_option_pcr_loop', ['etf_option_pcr']),
                            ('equity_bond_loop', ['equity_bond']),
                            ('index_technical_loop', ['index_technical'])]:
            with self.subTest(loop=name):
                app = App.__new__(App)
                app.stop = clock = Clock()
                for i, attr in enumerate(attrs):
                    setattr(app, attr, Service(str(i)))
                with patch('core.app.now_cn', side_effect=lambda: clock.now):
                    getattr(app, name)()
                self.assertEqual(clock.waits, [600, 3600, 3600])
                for attr in attrs:
                    self.assertEqual([c.strftime('%H:%M') for c in getattr(app, attr).calls], ['16:20', '16:30'])

    def test_unpublished_pcr_retries_without_accelerating_network_failures(self):
        app = App.__new__(App)
        app.stop = clock = Clock()
        clock.now = clock.now.replace(hour=16, minute=30)
        class Failing(Service):
            def __init__(self, code, error):
                super().__init__(code)
                self.failure = error
            def refresh(self, now):
                super().refresh(now)
                self.error = self.failure
        app.option_pcr = Failing('510050', NOT_PUBLISHED)
        app.option_pcr_300 = Failing('510300', '连接失败')
        with patch('core.app.now_cn', side_effect=lambda: clock.now), patch('core.app.time.monotonic', side_effect=lambda: clock.now.timestamp()):
            app.option_pcr_loop()
        self.assertEqual(clock.waits, [600, 600, 600])
        self.assertEqual(len(app.option_pcr.calls), 3)
        self.assertEqual(len(app.option_pcr_300.calls), 1)

    def test_pcr_stops_retrying_after_success_for_both_products(self):
        app = App.__new__(App)
        app.stop = clock = Clock()
        clock.now = clock.now.replace(hour=16, minute=30)
        class Recovering(Service):
            def refresh(self, now):
                super().refresh(now)
                self.error = NOT_PUBLISHED if len(self.calls) == 1 else ''
        app.option_pcr = Recovering('510050')
        app.option_pcr_300 = Recovering('510300')
        with patch('core.app.now_cn', side_effect=lambda: clock.now), patch('core.app.time.monotonic', side_effect=lambda: clock.now.timestamp()):
            app.option_pcr_loop()
        self.assertEqual(clock.waits, [600, 3600, 3600])
        self.assertEqual(len(app.option_pcr.calls), 2)
        self.assertEqual(len(app.option_pcr_300.calls), 2)

    def test_index_reference_retries_failure_then_returns_to_hourly_checks(self):
        app = App.__new__(App)
        app.stop = clock = Clock()
        clock.now = clock.now.replace(hour=16, minute=30)
        class Recovering(Service):
            def refresh(self, now):
                super().refresh(now)
                self.error = '连接失败' if len(self.calls) == 1 else ''
        app.index_technical = Recovering()
        with patch('core.app.now_cn', side_effect=lambda: clock.now):
            app.index_technical_loop()
        self.assertEqual(clock.waits, [300, 3600, 3600])
        self.assertEqual([c.strftime('%H:%M') for c in app.index_technical.calls], ['16:30', '16:35'])


if __name__ == '__main__':
    unittest.main()
