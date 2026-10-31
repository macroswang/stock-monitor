import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from core.app import App, breadth_close_date, breadth_collection_due


def closed_record(day):
    return {'status': 'closed', 'date': day, 'expected': 2, 'covered': 2, 'missing': 0,
            'advance': 1, 'decline': 1, 'flat': 0, 'suspended': 0,
            'first_quote': day+'T15:00:00+08:00', 'last_quote': day+'T15:00:00+08:00',
            'collected_at': day+'T15:15:00+08:00'}


class BreadthScheduleTests(unittest.TestCase):
    def test_close_boundary_and_holiday(self):
        self.assertEqual(breadth_close_date(datetime.fromisoformat('2026-10-29T15:14:59+08:00')), '2026-10-28')
        self.assertEqual(breadth_close_date(datetime.fromisoformat('2026-10-29T15:15:00+08:00')), '2026-10-29')
        self.assertEqual(breadth_close_date(datetime.fromisoformat('2026-10-31T10:00:00+08:00')), '2026-10-30')

    def test_failed_close_retries_at_most_every_30_minutes(self):
        now = datetime.fromisoformat('2026-10-29T18:00:00+08:00')
        self.assertTrue(breadth_collection_due(now, False, True, None))
        self.assertFalse(breadth_collection_due(now, False, True, 1799))
        self.assertTrue(breadth_collection_due(now, False, True, 1800))
        self.assertFalse(breadth_collection_due(now, False, False, 1800))
        self.assertTrue(breadth_collection_due(now.replace(hour=14), False, False, 0))

    def test_holiday_does_not_poll_as_live_but_can_recover_a_missing_close(self):
        holiday = datetime.fromisoformat('2026-10-05T10:00:00+08:00')
        self.assertFalse(breadth_collection_due(holiday, False, False, None))
        self.assertTrue(breadth_collection_due(holiday, True, False, None))
        self.assertTrue(breadth_collection_due(holiday, False, True, 1800))
        self.assertFalse(breadth_collection_due(holiday, False, True, 1799))

    def test_loop_recovers_after_close_failure_without_extra_poll(self):
        dates = iter(datetime.fromisoformat(t) for t in [
            '2026-10-29T15:14:00+08:00', '2026-10-29T15:19:00+08:00',
            '2026-10-29T15:24:00+08:00', '2026-10-29T15:49:00+08:00'])
        ticks = iter([0, 0, 300, 300, 600, 600, 2100, 2100])
        closed = {'2026-10-28'}
        class Store:
            def getcache(self, code, kind, day):
                return [{'data': closed_record(day)}] if day in closed else []
        class Collector:
            calls = 0
            def refresh(self):
                self.calls += 1
                if self.calls == 3:
                    closed.add('2026-10-29')
        class Stop:
            count = 0
            def is_set(self): return self.count >= 4
            def wait(self, seconds):
                self.count += 1
                self.assert_wait(seconds)
            def assert_wait(self, seconds):
                if seconds != 180: raise AssertionError(seconds)
        collector = Collector()
        app = SimpleNamespace(store=Store(), breadth=collector, stop=Stop())
        with patch('core.app.now_cn', side_effect=lambda: next(dates)), \
             patch('core.app.time.monotonic', side_effect=lambda: next(ticks)):
            App.breadth_loop(app)
        self.assertEqual(collector.calls, 3)
        self.assertIn('2026-10-29', closed)

    def test_scan_time_is_subtracted_and_slow_scan_still_pauses(self):
        for duration, expected in ((105, 75), (250, 15)):
            with self.subTest(duration=duration):
                class Stop:
                    done = False
                    waited = None
                    def is_set(self): return self.done
                    def wait(self, seconds): self.waited, self.done = seconds, True
                class Store:
                    def getcache(self, _code, _kind, day): return [{'data': closed_record(day)}]
                class Collector:
                    def refresh(self): pass
                stop = Stop()
                app = SimpleNamespace(store=Store(), breadth=Collector(), stop=stop)
                with patch('core.app.now_cn', return_value=datetime.fromisoformat('2026-10-30T13:10:00+08:00')), \
                     patch('core.app.time.monotonic', side_effect=[0, duration]):
                    App.breadth_loop(app)
                self.assertEqual(stop.waited, expected)

    def test_invalid_closed_cache_is_retried_at_the_normal_recovery_interval(self):
        dates = iter(datetime.fromisoformat(t) for t in [
            '2026-10-29T18:00:00+08:00', '2026-10-29T18:05:00+08:00',
            '2026-10-29T18:30:00+08:00'])
        ticks = iter([0, 0, 300, 300, 1800, 1800])
        class Store:
            def getcache(self, _code, _kind, day):
                return [{'data': {**closed_record(day), 'missing': 1}}]
        class Collector:
            calls = 0
            def refresh(self): self.calls += 1
        class Stop:
            count = 0
            def is_set(self): return self.count >= 3
            def wait(self, _seconds): self.count += 1
        collector = Collector()
        app = SimpleNamespace(store=Store(), breadth=collector, stop=Stop())
        with patch('core.app.now_cn', side_effect=lambda: next(dates)), \
             patch('core.app.time.monotonic', side_effect=lambda: next(ticks)):
            App.breadth_loop(app)
        self.assertEqual(collector.calls, 2)


if __name__ == '__main__':
    unittest.main()
