import unittest
from contextlib import nullcontext
from unittest.mock import Mock,patch

from core import brokers
from executor.adb import Node
from executor.brokers.base import BrokerCredentials
from executor.holdings import collect
from executor.orderbook import parse_positions


def node(text='',rid='',bounds=(0,0,500,500)):
    return Node(text,rid,'android.view.View',bounds,False,True,False,False)


class ListDevice:
    def __init__(self,pages,start=0):self.pages=pages;self.index=start
    def nodes(self):return [node(rid='holdings')]+[node(json,'row') for json in self.pages[self.index]]
    def shell(self,*args):
        down=int(args[3])<int(args[5])
        self.index=max(0,self.index-1) if down else min(len(self.pages)-1,self.index+1)


def parse(nodes,_bounds):
    rows=[]
    for n in nodes:
        if n.resource_id=='row':
            name,quantity=n.text.split(':');rows.append(dict(name=name,quantity=int(quantity),sellable=int(quantity)))
    return rows


class HoldingsTraversalTests(unittest.TestCase):
    def test_account_change_during_pagination_aborts_snapshot(self):
        adb=ListDevice([['A:100'],['B:200']])
        verify=Mock(side_effect=[None,ValueError('当前账户已变化')])
        with self.assertRaisesRegex(ValueError,'账户'):
            collect(adb,adb.nodes(),'holdings',parse,{},verify=verify)
        self.assertEqual(verify.call_count,2)

    def test_read_from_middle_returns_to_top_collects_all_and_deduplicates_overlap(self):
        adb=ListDevice([['A:100','B:200'],['B:200','C:300']],start=1)
        result=collect(adb,adb.nodes(),'holdings',parse,{'available':'1000'})
        self.assertTrue(result['complete'])
        self.assertEqual([r['name'] for r in result['positions']],['A','B','C'])

    def test_changed_quantity_during_scan_is_not_a_complete_snapshot(self):
        adb=ListDevice([['A:100','B:200'],['B:300','C:300']])
        with self.assertRaisesRegex(ValueError,'发生变化'):collect(adb,adb.nodes(),'holdings',parse,{})

    def test_empty_requires_explicit_empty_holdings_message(self):
        adb=ListDevice([[]])
        self.assertFalse(collect(adb,adb.nodes(),'holdings',parse,{})['complete'])
        self.assertTrue(collect(adb,adb.nodes()+[node('暂无持仓')],'holdings',parse,{})['complete'])

    def test_disappearing_list_is_an_error_not_clearance(self):
        adb=ListDevice([['A:100']])
        adb.nodes=Mock(return_value=[])
        with self.assertRaisesRegex(ValueError,'离开'):collect(adb,[node(rid='holdings'),node('A:100','row')],'holdings',parse,{})

    def test_six_digit_market_value_is_never_a_security_code(self):
        rows=parse_positions([node(rid='content_layout'),node('山子高科','stock_name'),node('123456','stock_code')])
        self.assertEqual(rows[0]['code'],'')


class IdentityBoundaryTests(unittest.TestCase):
    def test_verified_flag_does_not_override_wrong_account_display(self):
        store=Mock();store.query.return_value=[{'account':'987654321'}]
        client=Mock();client.ensure_ready.return_value=dict(account_verified=True,account_display='987654321')
        with self.assertRaisesRegex(brokers.BrokerError,'不一致'):
            brokers._verify_account(client,BrokerCredentials('zhangle','123456789'),store)

    def test_holdings_identity_is_checked_before_and_after_read(self):
        store=Mock();store.query.side_effect=lambda sql,args=():[{'account':'123456789'}] if 'SELECT account FROM broker_accounts' in sql else []
        client=Mock();client.holdings.return_value=dict(positions=[],complete=True)
        client.ensure_ready.side_effect=[dict(account_verified=True,account_display='123456789'),dict(account_verified=True,account_display='987654321')]
        with patch('core.brokers.device_operation',return_value=nullcontext()),patch('core.brokers._adapter',return_value=({},BrokerCredentials('zhangle','123456789'),client)):
            with self.assertRaisesRegex(brokers.BrokerError,'不一致'):brokers.holdings(store,'account-a')
        self.assertEqual(client.ensure_ready.call_count,2)

    def test_resolver_runs_once_per_unique_row_and_preserves_overlap_codes(self):
        adb=ListDevice([['A:100','B:200'],['B:200','C:300']])
        resolve=Mock(side_effect=lambda row,nodes:dict(row,code={'A':'000001','B':'000002','C':'000003'}[row['name']]))
        result=collect(adb,adb.nodes(),'holdings',parse,{},resolve=resolve)
        self.assertTrue(result['complete'])
        self.assertEqual(resolve.call_count,3)
        self.assertEqual([r['code'] for r in result['positions']],['000001','000002','000003'])

class TargetPositionTests(unittest.TestCase):
    def test_targeted_read_is_not_a_full_snapshot_and_never_swipes_other_positions(self):
        adb=ListDevice([['A:100','B:200'],['C:300']]);adb.shell=Mock(side_effect=AssertionError('Must not swipe'))
        resolved=Mock(side_effect=lambda row,ns:dict(row,code='000981'))
        r=collect(adb,adb.nodes(),'holdings',parse,{'available':'5000'},resolve=resolved,target_code='sz000981',target_name='B')
        self.assertTrue(r['position_only']);self.assertFalse(r['complete']);self.assertEqual(r['positions'][0]['quantity'],200)
        self.assertEqual(resolved.call_count,1);adb.shell.assert_not_called()
    def test_targeted_read_rejects_changed_quantity(self):
        adb=ListDevice([['A:100']]);first=adb.nodes();adb.nodes=Mock(return_value=[node(rid='holdings'),node('A:200','row')])
        with self.assertRaisesRegex(ValueError,'变化'):collect(adb,first,'holdings',parse,{},resolve=lambda row,ns:dict(row,code='000981'),target_code='000981',target_name='A')
