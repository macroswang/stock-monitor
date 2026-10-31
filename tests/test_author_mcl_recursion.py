import json
import unittest
from pathlib import Path

from scripts.compare_author_mcl_recursion import compare


class AuthorMclRecursionTests(unittest.TestCase):
    def test_conditional_comparison_and_mixed_sources(self):
        author=json.loads(Path('fixtures/author-mcl-reference.json').read_text())
        breadth=json.loads(Path('public/breadth-preview.json').read_text())['days']
        results=compare(author,breadth)
        self.assertEqual([r['date'] for r in results],['2026-09-22','2026-09-23','2026-09-24','2026-10-26','2026-10-27','2026-10-28'])
        oct27=next(r for r in results if r['date']=='2026-10-27')
        self.assertAlmostEqual(oct27['conditional'], -280.905)
        self.assertAlmostEqual(results[-1]['conditional'], -82.91)
        self.assertLess(max(abs(r['difference']) for r in results),.7)
        self.assertNotEqual(oct27['prior_breadth_source'],oct27['current_breadth_source'])

    def test_missing_or_incomplete_day_not_used(self):
        author=json.loads(Path('fixtures/author-mcl-reference.json').read_text())
        breadth=json.loads(Path('public/breadth-preview.json').read_text())['days']
        for row in breadth:
            if row['date']=='2026-10-26': row['missing']=1
        self.assertNotIn('2026-10-27',[r['date'] for r in compare(author,breadth)])
        self.assertNotIn('2026-10-26',[r['date'] for r in compare(author,breadth)])

    def test_recurrence_matches_two_ema_computation(self):
        xs=[140,-800,1800,-300,900]
        fast=slow=400.0
        m=[]
        for x in xs:
            fast=.1*x+.9*fast;slow=.05*x+.95*slow;m.append(fast-slow)
        for i in range(2,len(xs)):
            self.assertAlmostEqual(m[i],1.85*m[i-1]-.855*m[i-2]+.05*(xs[i]-xs[i-1]))


if __name__=='__main__':
    unittest.main()
