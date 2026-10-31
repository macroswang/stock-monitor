import unittest

from scripts.analyze_trin_crosssections import compute, reconcile


def row(symbol, close, previous, volume, amount):
    return {
        'symbol': symbol, 'open': '10', 'high': '12', 'low': '8',
        'close': close, 'pre_close': previous, 'vol': volume, 'amount': amount,
    }


class TrinCrossSectionTests(unittest.TestCase):
    def test_share_and_amount_calculations_and_market_scope(self):
        rows = [
            row('600001.SH', '11', '10', '10', '11'),
            row('000001.SZ', '9', '10', '2', '1.8'),
            row('000002.SZ', '9', '10', '3', '2.7'),
            row('830001.BJ', '11', '10', '5', '5.5'),
            row('689009.SH', '10', '10', '5', '5'),
        ]
        result = compute(rows, {'SH', 'SZ'}, include_cdr=False)
        self.assertEqual(result['counts'], {'up': 1, 'down': 2})
        self.assertEqual(result['up_volume_shares'], '1000')
        self.assertEqual(result['down_volume_shares'], '500')
        self.assertEqual(result['trin_volume'], 0.25)
        self.assertAlmostEqual(result['trin_amount'], 4.5 / 22)
        self.assertEqual(compute(rows, {'SH', 'SZ'})['counts']['flat'], 1)
        self.assertEqual(compute(rows, {'SH', 'SZ', 'BJ'})['counts']['up'], 2)

    def test_rejects_inconsistent_units_and_detects_disagreement(self):
        bad = row('600001.SH', '11', '10', '10', '1000')
        self.assertIsNone(compute([bad], {'SH'})['trin_volume'])
        self.assertEqual(compute([bad], {'SH'})['invalid'], ['600001.SH'])
        source = row('600001.SH', '11', '10', '10', '11')
        bao = {'daily': [{'code': 'sh.600001', 'tradestatus': '1',
                           'open': '10', 'high': '12', 'low': '8', 'close': '10',
                           'preclose': '10', 'volume': '1000', 'amount': '11000'}]}
        result = reconcile([source], bao)
        self.assertEqual(result['compared'], 1)
        self.assertEqual(result['mismatches'][0]['fields'], ['close'])


if __name__ == '__main__':
    unittest.main()
