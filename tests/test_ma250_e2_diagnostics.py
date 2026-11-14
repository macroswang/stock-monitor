"""Financial and temporal controls for the separate E2 diagnosis."""
import unittest

from research.ma250_e2_diagnostics import (attribution, cash_blend, exposure_control,
                                          reschedule, thinning, stats)
from research.ma250_optimization import Portfolio
from tests.test_ma250_optimization import bars, event


class E2DiagnosticControls(unittest.TestCase):
    def test_selection_timing_identity_and_rejected_cohort(self):
        bs=bars(30)
        accepted=event(bs);accepted['exit_price']=12.
        rejected=dict(event(bs),code='other',exit_price=8.)
        actual=dict(accepted,entry=11.,entry_date=bs[1]['date'])
        r=attribution([accepted,rejected],[actual])
        self.assertEqual(r['accepted_baseline_counterfactual']['n'],1)
        self.assertEqual(r['rejected_baseline_counterfactual']['n'],1)
        self.assertAlmostEqual(r['selection_mean_pp']+r['timing_and_rolled_exit_mean_pp'],r['total_mean_pp'])
        self.assertLess(r['timing_and_rolled_exit_mean_pp'],0)

    def test_pending_outcomes_are_not_zero_returns(self):
        bs=bars(30);pending=dict(event(bs),exit_date=None,exit_price=None)
        self.assertEqual(stats([pending])['n'],0)
        self.assertIsNone(stats([pending])['mean'])

    def test_cash_blend_preserves_cash_and_scales_pnl(self):
        curve=[('2020-01-01',1_100_000.,.5),('2020-01-02',900_000.,.6)]
        reduced=cash_blend(curve,.5)
        self.assertEqual([r[1] for r in reduced],[1_050_000.,950_000.])
        self.assertAlmostEqual(reduced[0][2],275_000/1_050_000)
        target=[(d,v,.2) for d,v,_ in curve]
        result=exposure_control(curve,target)
        self.assertAlmostEqual(result['result']['exposure'],.2)
        self.assertAlmostEqual(result['result']['total'],-10*result['weight'])

    def test_delayed_entry_restarts_horizon_and_uses_raw_lots(self):
        bs=bars(35)
        for b in bs:b['execution']=dict(b,open=20.,close=20.,high=20.6,low=19.6)
        raw={b['date']:b['execution'] for b in bs}
        e=event(bs,entry=1,exit_=20);e.update(entry=20.,factor=2.,stop=18.)
        delayed,status=reschedule(e,bs,raw,[b['date'] for b in bs],delay=2,hold=20)
        self.assertEqual(status,'entered')
        self.assertEqual(delayed['entry_date'],bs[3]['date'])
        self.assertEqual(delayed['exit_date'],bs[22]['date'])
        self.assertEqual(delayed['entry'],20.)
        self.assertEqual(delayed['exit_price'],20.)
        self.assertEqual(delayed['factor'],2.)

    def test_suspended_or_locked_scheduled_entry_is_not_retried(self):
        bs=bars(35);e=event(bs,entry=1,exit_=20)
        raw={b['date']:b for b in bs};bs[3].update(open=11.,high=11.,low=11.,close=11.)
        row,status=reschedule(e,bs,raw,[b['date'] for b in bs],delay=2)
        self.assertIsNone(row);self.assertEqual(status,'entry_unavailable')
        del raw[bs[3]['date']]
        reduced=bs[:3]+bs[4:]
        row,status=reschedule(e,reduced,raw,[b['date'] for b in bs],delay=2)
        self.assertIsNone(row);self.assertEqual(status,'entry_unavailable')

    def test_thinning_is_reproducible_without_changing_events(self):
        bs=bars(30);a=event(bs,entry=1,exit_=20);b=dict(a,code='other')
        series={a['code']:bs,b['code']:bs};context=Portfolio(series)
        before=[dict(a),dict(b)]
        left=thinning(context,[a,b],[a],repetitions=5)
        right=thinning(context,[a,b],[a],repetitions=5)
        self.assertEqual(left,right);self.assertEqual(left['matched_source_count'],1)
        self.assertEqual([a,b],before)


if __name__=='__main__':unittest.main()
