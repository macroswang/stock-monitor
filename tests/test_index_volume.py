import copy,tempfile,unittest
from unittest.mock import patch
from core.app import App
from core.index_volume import index_direction,normalize_index_minute

CODE='sh000001';DAY='2026-11-04'
def sample():
    raw=dict(code=CODE,day=DAY,time='10:30',source='TEST_ONLY_DIRECTION_SOURCE',unit='lots',scope='index_total',basis='trade_initiator',complete=True,total_lots=1000,buy_lots=600,sell_lots=250,neutral_lots=100,unknown_lots=50)
    return dict(time='10:30',close='3680',volume_lots=1000,volume_direction=raw)

class IndexVolumeTests(unittest.TestCase):
    def test_direction_requires_exact_identity_units_scope_and_full_reconciled_volume(self):
        bar=sample();self.assertEqual(index_direction(CODE,DAY,bar),bar['volume_direction'])
        for key,value in [('code','sz399001'),('day','2026-11-03'),('time','10:31'),('unit','yuan'),('scope','sample_stocks'),('basis','price_change'),('complete',False),('source',''),('buy_lots',601),('sell_lots',True),('neutral_lots',-1),('unknown_lots',50.5),('total_lots',1001)]:
            with self.subTest(key=key):
                changed=copy.deepcopy(bar);changed['volume_direction'][key]=value
                self.assertIsNone(index_direction(CODE,DAY,changed))
        for stamp in ('12:00','13:00','10:99'):
            changed=copy.deepcopy(bar);changed['time']=changed['volume_direction']['time']=stamp
            self.assertIsNone(index_direction(CODE,DAY,changed))
    def test_unknown_does_not_infer_sides_from_a_price_rise_or_zero_direction_counts(self):
        group=dict(date=DAY,bars=[dict(time='10:30',close='3680',volume_lots=1000),dict(time='10:31',close='3700',volume_lots=1200)])
        result=normalize_index_minute(group,CODE)
        self.assertEqual(result['direction_status'],'unavailable');self.assertEqual(result['bars'],group['bars'])
    def test_partial_cache_is_normalized_read_only_and_preserves_totals(self):
        bar=sample();bad=copy.deepcopy(bar);bad['time']='10:31';bad['volume_direction']['buy_lots']=800
        group=dict(date=DAY,bars=[bar,bad]);before=copy.deepcopy(group);result=normalize_index_minute(group,CODE)
        self.assertEqual(group,before);self.assertEqual(result['direction_status'],'partial')
        self.assertIn('volume_direction',result['bars'][0]);self.assertNotIn('volume_direction',result['bars'][1])
        self.assertEqual([r['volume_lots'] for r in result['bars']],[1000,1000])
    def test_app_rpc_keeps_index_date_scoped_and_never_fetches_direction_on_ui_requests(self):
        with tempfile.TemporaryDirectory() as directory:
            app=App(directory,start_worker=False)
            try:
                app.store.cache(CODE,'market_minute',DAY,dict(date=DAY,previous_close='3600',bars=[sample()]))
                with patch('core.market.minutes',side_effect=AssertionError('UI must not fetch')):
                    self.assertEqual(app.call('index_minute',dict(code=CODE,day=DAY))['minute']['direction_status'],'complete')
                    self.assertEqual(app.call('market',dict(day=DAY))['minute']['direction_status'],'complete')
                    self.assertIsNone(app.call('index_minute',dict(code='sz399001',day=DAY))['minute'])
                    self.assertIsNone(app.call('index_minute',dict(code=CODE,day='2026-11-03'))['minute'])
            finally:app.stop.set();app.store.db.close()
