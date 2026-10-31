import unittest
from scripts.check_beijing_block_examples import compare


class BeijingBlockExamplesTest(unittest.TestCase):
    def test_positive_difference_and_rounding_are_compared(self):
        sample=[{'date':'20260324','code':'920368','volume':1100000,'amount':33000000,'url':'https://example.test'}]
        source={'rows':[{'date':'20260324','bar_mismatches':{'920368':{
            'tdx_shares':15347690,'money_shares':'14247690',
            'tdx_amount_yuan':'591507648','money_amount_yuan':'558507632'}}}]}
        out=compare(sample,source)[0]
        self.assertTrue(out['volume_matches'])
        self.assertTrue(out['amount_matches_within_32_yuan'])
        source['rows'][0]['bar_mismatches']['920368']['tdx_shares']-=1
        self.assertFalse(compare(sample,source)[0]['volume_matches'])


if __name__=='__main__':unittest.main()
