import unittest
from scripts.crosscheck_march_beijing_sina import interpret


class SinaBeijingTest(unittest.TestCase):
    def test_exact_volume_comparison_and_missing_date(self):
        text='var result=([{"day":"2026-03-24","open":"1","high":"2","low":"1","close":"2","volume":"15347690"}]);'
        result=interpret(text,'2026-03-24','14247690','15347690')
        self.assertTrue(result['matches_tdx_volume'])
        self.assertFalse(result['matches_money_volume'])
        self.assertFalse(result['turnover_available'])
        with self.assertRaises(ValueError):interpret(text,'2026-03-25','1','2')


if __name__=='__main__':unittest.main()
