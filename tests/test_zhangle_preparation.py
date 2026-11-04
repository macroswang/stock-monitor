"""Native input recovery uses a fake device; no submit button is ever touched."""
import json
import unittest
from dataclasses import replace
from unittest.mock import patch

from executor.adb import parse_nodes
from executor.runtime import bound_timeout, budget
from executor.trade import (TradePage, TradePreparationError, CODE_ID, SEARCH_CODE_ID,
                            FIELD_ID, SUBMIT_ID, read_form)
from tests.test_executor_trade import EMPTY_SELL_XML, SELL_XML, TRADE_FOCUS, DialogTests


def poll(check, timeout, interval):
    for _ in range(4):
        value=check()
        if value:return value
    return None


class InputDevice:
    def __init__(self, drops=0, clear_failures=0, focus_delay=0, side='sell'):
        self.code='';self.price='';self.quantity='';self.search=False;self.search_text=''
        self.focus=None;self.focus_delay=focus_delay;self.drops=drops;self.clear_failures=clear_failures
        self.inputs=[];self.taps=[];self.clears=[];self.wrong_side=False;self.dialog=False
        self.after_input=None;self.after_clear=None
        self.side=side

    def current_focus(self):
        bound_timeout(20)
        return TRADE_FOCUS

    def nodes(self):
        bound_timeout(20)
        fields=parse_nodes(EMPTY_SELL_XML.replace('卖出','买入') if self.side=='buy' else EMPTY_SELL_XML)
        result=[]
        for n in fields:
            suffix=n.resource_id.rsplit('/',1)[-1]
            if suffix==CODE_ID:n=replace(n,text=self.code+' 山子高科' if self.code else n.text)
            elif suffix==FIELD_ID:
                key='price' if n.bounds[1]==378 else 'quantity'
                n=replace(n,text=getattr(self,key) or n.text,focused=self.focus==key)
            elif suffix=='tv_max_volume':n=replace(n,text='10100' if self.code else '--')
            elif suffix=='tv_max_volume_label':n=replace(n,text='可买' if self.side=='buy' else '可卖')
            if self.wrong_side and suffix==SUBMIT_ID:n=replace(n,text='买入')
            result.append(n)
        if self.search:
            self.focus_delay=max(0,self.focus_delay-1)
            result.append(replace(fields[0],resource_id='com.lphtsccft:id/'+SEARCH_CODE_ID,
                text=self.search_text or '请输入代码/名称/拼音',focused=self.focus=='search' and self.focus_delay==0))
        if self.dialog:result+=parse_nodes(DialogTests.CONFIRM_XML)
        return result

    def tap_node(self,node):
        bound_timeout(20);suffix=node.resource_id.rsplit('/',1)[-1];self.taps.append(suffix)
        if suffix==CODE_ID:self.search=True;self.focus='search'
        elif suffix==SEARCH_CODE_ID:self.focus='search'
        elif suffix==FIELD_ID:self.focus='price' if node.bounds[1]==378 else 'quantity'
        else:raise AssertionError('Preparation must never touch a submission or dialog button')

    def clear_text(self,length):
        bound_timeout(20);self.clears.append(self.focus)
        assert self.focus in ('search','price','quantity') and not self.focus_delay
        if self.clear_failures:self.clear_failures-=1;return
        if self.focus=='search':self.search_text=''
        else:setattr(self,self.focus,'')
        if self.after_clear:self.after_clear()

    def input_text(self,value):
        bound_timeout(20);self.inputs.append((self.focus,value))
        assert self.focus in ('search','price','quantity') and not self.focus_delay
        if self.focus=='search':
            self.search_text=value
            if self.drops:self.drops-=1
            else:self.code=value;self.price='2.20';self.search=False;self.focus=None
        else:setattr(self,self.focus,value)
        if self.after_input:self.after_input()


class PreparationTests(unittest.TestCase):
    def setUp(self):
        p=patch('executor.trade.wait_until',side_effect=poll);p.start();self.addCleanup(p.stop)

    def test_popup_editor_gets_focus_before_input_and_all_fields_read_back(self):
        adb=InputDevice(focus_delay=3);page=TradePage(adb)
        form=page.preview('sell','000981',2300,'2.21')
        self.assertEqual((form.side,form.code,form.price,form.quantity),('sell','000981','2.21','2300'))
        self.assertEqual(adb.inputs,[('search','000981'),('price','2.21'),('quantity','2300')])
        self.assertNotIn(SUBMIT_ID,adb.taps)
        self.assertTrue(any(s['focused_id']==SEARCH_CODE_ID for s in page.preparation))

    def test_lost_first_code_input_is_refocused_cleared_and_recovered_once(self):
        adb=InputDevice(drops=1);page=TradePage(adb)
        form=page.preview('sell','000981',2300,'2.20')
        self.assertEqual(form.code,'000981');self.assertEqual(form.quantity,'2300')
        self.assertEqual(adb.inputs.count(('search','000981')),2)
        self.assertEqual(adb.clears,['search'])
        self.assertTrue(any(s['stage']=='code_recover' and s['attempt']==2 for s in page.preparation))
        self.assertNotIn(SUBMIT_ID,adb.taps)

    def test_buy_form_uses_the_same_recovery_without_switching_side(self):
        adb=InputDevice(drops=1,side='buy');page=TradePage(adb)
        form=page.preview('buy','000981',100,'2.21')
        self.assertEqual((form.side,form.code,form.quantity,form.max_label),('buy','000981','100','可买'))
        self.assertEqual(adb.inputs.count(('search','000981')),2);self.assertNotIn(SUBMIT_ID,adb.taps)

    def test_uncleared_search_never_appends_a_code_to_old_text(self):
        adb=InputDevice(clear_failures=1);adb.search=True;adb.search_text='600519';adb.focus='search'
        page=TradePage(adb);page.set_code('000981')
        self.assertEqual(adb.clears,['search','search']);self.assertEqual(adb.inputs,[('search','000981')])

    def test_permanent_input_failure_is_bounded_and_preserves_partial_readback(self):
        adb=InputDevice(drops=10);page=TradePage(adb)
        with self.assertRaises(TradePreparationError) as caught:page.preview('sell','000981',2300,'2.20')
        trace=caught.exception.diagnostics
        self.assertEqual(trace['stage'],'code');self.assertEqual(trace['attempts'],2)
        self.assertEqual(adb.inputs,[('search','000981'),('search','000981')])
        self.assertTrue(any(s['editor_value']=='000981' for s in trace['steps']))
        self.assertNotIn(SUBMIT_ID,adb.taps)

    def test_wrong_side_and_existing_confirmation_stop_without_recovery_or_submit(self):
        for mode in ('wrong_side','dialog'):
            adb=InputDevice();page=TradePage(adb)
            def change():setattr(adb,mode,True)
            adb.after_input=change
            with self.assertRaises(TradePreparationError):page.set_code('000981')
            self.assertEqual(len(adb.inputs),1);self.assertEqual(adb.taps,[CODE_ID])

    def test_price_edit_cannot_continue_after_stock_changes(self):
        adb=InputDevice();adb.code='000981';adb.price='2.20';adb.after_clear=lambda:setattr(adb,'code','600519')
        page=TradePage(adb)
        with self.assertRaisesRegex(TradePreparationError,'股票代码发生变化'):page._fill(0,'2.21')
        self.assertEqual(adb.inputs,[])

    def test_outer_execution_deadline_stops_input_recovery(self):
        clock=[100.]
        adb=InputDevice();page=TradePage(adb)
        adb.after_input=lambda:clock.__setitem__(0,103.)
        with patch('time.monotonic',side_effect=lambda:clock[0]):
            with budget(2):
                with self.assertRaises(TradePreparationError):page.set_code('000981',timeout=2)
        self.assertEqual(len(adb.inputs),1)

    def test_missing_quote_is_not_mistaken_for_ready_just_because_code_matches(self):
        adb=InputDevice(drops=10);adb.code='000981';adb.price='';page=TradePage(adb)
        with self.assertRaises(TradePreparationError):page.set_code('000981')
        self.assertTrue(adb.inputs)

    def test_code_parser_accepts_native_spacing_but_not_extra_digits(self):
        for text in ('000981 山子高科','000981\u00a0山子高科','000981\n山子高科','000981山子高科','000981'):
            nodes=parse_nodes(SELL_XML.replace('000981 山子高科',text));self.assertEqual(read_form(nodes).code,'000981')
        for text in ('0009811','1000981','00098','code000981'):
            nodes=parse_nodes(SELL_XML.replace('000981 山子高科',text));self.assertEqual(read_form(nodes).code,'')

    def test_failure_trace_never_copies_password_or_dialog_account_text(self):
        adb=InputDevice();page=TradePage(adb);secret='9876543210'
        nodes=[replace(n,password=True,text=secret,focused=True) for n in parse_nodes(SELL_XML)]
        nodes+=parse_nodes(DialogTests.CONFIRM_XML)
        page._record_preparation('code_failed',1,TRADE_FOCUS,nodes)
        encoded=json.dumps(page.preparation)
        self.assertNotIn(secret,encoded);self.assertNotIn('0169721247',encoded)
