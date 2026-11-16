import concurrent.futures
import json
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path

from core import chart_drawings as drawings
from core.app import App
from core.store import Store


def shape(key='a', kind='line'):
    return dict(id=key, kind=kind, points=[dict(date='2026-11-09', price=10.25), dict(date='2026-11-16', price=12.5)])


class ChartDrawingsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'monitor.sqlite3'
        self.store = Store(self.path)
        self.addCleanup(self.store.db.close)

    def test_rpc_persists_across_store_restart_and_database_backup(self):
        app = App.__new__(App)
        app.store = self.store
        args = dict(code='sh603938', frame='daily')
        self.assertEqual(app.call('chart_drawings', args), dict(revision=0, items=[]))
        saved = app.call('chart_drawings_save', dict(**args, revision=0, items=[shape()]))
        reopened = Store(self.path)
        try:
            self.assertEqual(drawings.load(reopened, **args), saved)
        finally:
            reopened.db.close()
        target = sqlite3.connect(Path(self.tmp.name) / 'backup.sqlite3')
        try:
            self.store.db.backup(target)
            self.assertEqual(json.loads(target.execute('SELECT payload FROM chart_drawings').fetchone()[0]), [shape()])
        finally:
            target.close()

    def test_line_width_and_color_persist_and_invalid_styles_cannot_overwrite(self):
        item = dict(**shape(), color='#Ab12Ef', width=3)
        saved = drawings.save(self.store, 'sh603938', 'daily', 0, [item])
        self.assertEqual(saved['items'][0]['color'], '#ab12ef')
        self.assertEqual(saved['items'][0]['width'], 3)
        self.assertEqual(drawings.load(self.store, 'sh603938', 'daily'), saved)
        for key, value in [('color', 'red; script'), ('color', '#fff'), ('color', None), ('width', 0), ('width', 7), ('width', True), ('width', '3')]:
            invalid = dict(item)
            invalid[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                drawings.save(self.store, 'sh603938', 'daily', 1, [invalid])
        self.assertEqual(drawings.load(self.store, 'sh603938', 'daily'), saved)

    def test_rectangle_border_styles_survive_restart_and_update_without_moving_points(self):
        item = dict(**shape('rectangle', 'rect'), color='#Ab12Ef', width=4)
        drawings.save(self.store, 'sh603938', 'daily', 0, [item])
        reopened = Store(self.path)
        try:
            restored = drawings.load(reopened, 'sh603938', 'daily')
            self.assertEqual(restored['items'][0], dict(item, color='#ab12ef'))
            updated = dict(restored['items'][0], color='#1234ff', width=6)
            drawings.save(reopened, 'sh603938', 'daily', 1, [updated])
        finally:
            reopened.db.close()
        final = drawings.load(self.store, 'sh603938', 'daily')
        self.assertEqual(final['items'], [updated])
        self.assertEqual(final['items'][0]['points'], item['points'])
        self.assertEqual(drawings.load(self.store, 'sh603938', 'weekly')['items'], [])

    def test_stock_and_timeframe_are_isolated_and_deletion_is_durable(self):
        drawings.save(self.store, 'sh603938', 'daily', 0, [shape()])
        drawings.save(self.store, 'sh603938', 'weekly', 0, [shape('weekly', 'rect')])
        drawings.save(self.store, 'sz300364', 'daily', 0, [shape('other')])
        drawings.save(self.store, 'sh603938', 'daily', 1, [])
        self.assertEqual(drawings.load(self.store, 'sh603938', 'daily'), dict(revision=2, items=[]))
        self.assertEqual(drawings.load(self.store, 'sh603938', 'weekly')['items'][0]['id'], 'weekly')
        self.assertEqual(drawings.load(self.store, 'sz300364', 'daily')['items'][0]['id'], 'other')

    def test_stale_concurrent_writes_cannot_silently_replace_existing_annotations(self):
        def write(key):
            return drawings.save(self.store, 'sh603938', 'daily', 0, [shape(key)])
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(write, ['one', 'two']))
        self.assertEqual(sum(r.get('conflict', False) for r in results), 1)
        stored = drawings.load(self.store, 'sh603938', 'daily')
        self.assertEqual(stored['revision'], 1)
        self.assertEqual(len(stored['items']), 1)
        conflict = next(r for r in results if r.get('conflict'))
        self.assertEqual(conflict['items'], stored['items'])

    def test_independent_connections_have_atomic_compare_and_swap(self):
        other = Store(self.path)
        try:
            for i in range(60):
                barrier = threading.Barrier(2)
                code = f'sh{i:06d}'
                def write(pair):
                    store, name = pair
                    barrier.wait()
                    return drawings.save(store, code, 'daily', 0, [shape(name)])
                with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                    results = list(pool.map(write, [(self.store, 'one'), (other, 'two')]))
                self.assertEqual(sum(bool(r.get('conflict')) for r in results), 1)
                stored = drawings.load(self.store, code, 'daily')
                self.assertEqual(stored['revision'], 1)
                self.assertEqual(next(r for r in results if not r.get('conflict')), stored)
        finally:
            other.db.close()

    def test_retry_after_lost_reply_is_idempotent_but_newer_data_still_conflicts(self):
        items = [dict(**shape(), color='#ab12ef', width=4)]
        saved = drawings.save(self.store, 'sh603938', 'daily', 0, items)
        self.assertEqual(drawings.save(self.store, 'sh603938', 'daily', 0, items), saved)
        newer = drawings.save(self.store, 'sh603938', 'daily', 1, [shape('newer')])
        result = drawings.save(self.store, 'sh603938', 'daily', 0, items)
        self.assertTrue(result['conflict'])
        self.assertEqual(result['items'], newer['items'])

    def test_invalid_data_never_overwrites_saved_annotations(self):
        baseline = drawings.save(self.store, 'sh603938', 'daily', 0, [shape()])
        invalid = [None, {}, [shape()] * 201, [shape(), shape()]]
        for field, value in [('kind', 'ray'), ('id', '../unsafe'), ('points', []), ('points', [None, None])]:
            item = shape()
            item[field] = value
            invalid.append([item])
        for value in [float('inf'), float('nan'), -1, 0, True, '12', 1e10]:
            item = shape()
            item['points'][0]['price'] = value
            invalid.append([item])
        for value in ['2026-02-30', 'tomorrow', '2026-1-1']:
            item = shape()
            item['points'][0]['date'] = value
            invalid.append([item])
        item = shape(kind='rect')
        item['points'][1]['date'] = item['points'][0]['date']
        invalid.append([item])
        for items in invalid:
            with self.subTest(items=items), self.assertRaises((ValueError, TypeError)):
                drawings.save(self.store, 'sh603938', 'daily', 1, items)
        self.assertEqual(drawings.load(self.store, 'sh603938', 'daily'), baseline)
        for args in [('603938', 'daily'), ('sh603938', 'minute'), ('sh603938', None)]:
            with self.assertRaises(ValueError):
                drawings.load(self.store, *args)

    def test_valid_vertical_horizontal_lines_and_week_anchors(self):
        a = shape('vertical')
        a['points'][1]['date'] = a['points'][0]['date']
        b = shape('horizontal')
        b['points'][1]['price'] = b['points'][0]['price']
        result = drawings.save(self.store, 'sh603938', 'weekly', 0, [a, b])
        self.assertEqual(result['items'], [a, b])

    def test_drawing_writes_leave_rules_accounts_events_cache_and_config_unchanged(self):
        self.store.execute('INSERT INTO watch(code,name) VALUES(?,?)', ('sh603938', '三孚股份'))
        self.store.execute('INSERT INTO config VALUES(?,?)', ('trading_paused', 'true'))
        self.store.cache('sh603938', 'daily', '2026-11-13', dict(close='10'))
        tables = [r['name'] for r in self.store.query("SELECT name FROM sqlite_master WHERE type='table'") if r['name'] != 'chart_drawings']
        before = {name: self.store.query('SELECT * FROM '+name) for name in tables}
        drawings.save(self.store, 'sh603938', 'daily', 0, [shape()])
        drawings.save(self.store, 'sh603938', 'daily', 1, [])
        self.assertEqual({name: self.store.query('SELECT * FROM '+name) for name in tables}, before)

    def test_existing_database_gains_annotation_table_without_losing_data(self):
        self.store.execute('INSERT INTO watch(code,name) VALUES(?,?)', ('sz300364', '中文在线'))
        self.store.execute('DROP TABLE chart_drawings')
        reopened = Store(self.path)
        try:
            self.assertEqual(reopened.query('SELECT code,name FROM watch'), [dict(code='sz300364', name='中文在线')])
            self.assertEqual(drawings.load(reopened, 'sz300364', 'daily'), dict(revision=0, items=[]))
        finally:
            reopened.db.close()

    def test_corrupt_document_is_reported_instead_of_reset_to_empty(self):
        self.store.execute('INSERT INTO chart_drawings VALUES(?,?,?,?)', ('sh603938', 'daily', 1, '{broken'))
        with self.assertRaises(ValueError):
            drawings.load(self.store, 'sh603938', 'daily')
        self.assertEqual(self.store.query('SELECT payload FROM chart_drawings')[0]['payload'], '{broken')
