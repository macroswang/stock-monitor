import unittest
from decimal import Decimal

from scripts.research_author_score_linear import fit, predict


class LinearScoreExperimentTests(unittest.TestCase):
    def test_fit_and_prediction_on_known_coefficients(self):
        rows = [dict(p20=a,p60=b,p250=c,score=2+3*a-2*b+c) for a,b,c in
                [(0,0,0),(1,0,0),(0,1,0),(0,0,1),(1,2,3)]]
        model = fit(rows)
        self.assertEqual([round(x) for x in model], [2,3,-2,1])
        self.assertAlmostEqual(float(predict(model,dict(p20=2,p60=1,p250=4))),10.0)

    def test_singular_inputs_are_rejected(self):
        with self.assertRaises(ValueError):
            fit([dict(p20=1,p60=1,p250=1,score=1) for _ in range(5)])


if __name__ == '__main__':
    unittest.main()
