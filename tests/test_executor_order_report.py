import copy
import unittest
from unittest.mock import Mock,patch
from executor.order_report import field,validate_frames,ContractMismatch,zhangle_filled_orders
from executor.trade import OrderResult
from executor.ocr import OcrUnavailable,helper_binary


def cell(text,x,y,confidence=1):return dict(text=text,x=x,y=y,width=.15,height=.02,confidence=confidence)
def pair(label,value,y):return [cell(label,.1,y),cell(value,.65,y)]

class OrderEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.native=dict(name='示例股票',code='000981',side='sell',date='2026-11-02',time='10:14:18',quantity=600,price='2.140',filled=600,state='已成')
        self.top=[cell('委托明细',.3,.05),cell('000981',.1,.1),cell('卖出',.5,.1),cell('10:14:18',.1,.15),
                  *pair('委托数量','600',.2),*pair('委托价格','2.140',.25),*pair('成交数量','600',.3),*pair('备注','已成（卖出）',.35)]
        self.bottom=[*pair('股东账户','1234567890',.5),*pair('合同编号','69104',.6)]

    def validate(self,top=None,bottom=None,second=None,native=None,ident='69104',day='2026-11-02'):
        return validate_frames(top or self.top,bottom or self.bottom,second or self.bottom,native or self.native,ident,day)

    def test_agreement_with_native_row_and_two_ids_required(self):
        result=self.validate();self.assertEqual(result['status'],'filled');self.assertEqual(result['order_id'],'69104');self.assertEqual(len(result['evidence_hash']),64)
        self.assertNotIn('1234567890',str(result))

    def test_shareholder_account_never_used_as_contract(self):
        with self.assertRaises(ContractMismatch):self.validate(ident='1234567890')
        with self.assertRaises(ValueError):self.validate(bottom=pair('股东账户','69104',.6))

    def test_two_frames_with_different_id_rejected(self):
        with self.assertRaises(ValueError):self.validate(second=pair('合同编号','69105',.6))

    def test_low_confidence_id_or_field_rejected(self):
        for section,index in [('bottom',3),('top',4)]:
            rows=copy.deepcopy(getattr(self,section));rows[index]['confidence']=.98
            with self.subTest(section=section),self.assertRaises(ValueError):self.validate(**{section:rows})

    def test_ambiguous_id_cells_rejected(self):
        with self.assertRaises(ValueError):self.validate(bottom=self.bottom+[cell('99999',.85,.6)])

    def test_low_confidence_stock_side_or_time_rejected(self):
        for index in (0,1,2,3):
            rows=copy.deepcopy(self.top);rows[index]['confidence']=.8
            with self.subTest(index=index),self.assertRaises(ValueError):self.validate(top=rows)

    def test_native_code_side_qty_price_fill_state_time_day_mismatch(self):
        for change in [dict(code='603002'),dict(side='buy'),dict(quantity=500),dict(price='2.15'),dict(filled=500),dict(state='部成'),dict(time='10:14:19'),dict(date='2026-11-01')]:
            with self.subTest(change=change),self.assertRaises(ValueError):self.validate(native={**self.native,**change})

    def test_unknown_status_and_inconsistent_terminal_rejected(self):
        top=[*self.top[:-2],*pair('备注','已完成',.35)]
        with self.assertRaises(ValueError):self.validate(top=top)
        for native,fill in [(dict(state='已成'),500),(dict(state='废单'),100)]:
            n={**self.native,**native,'filled':fill}
            t=[*self.top[:8],*pair('成交数量',str(fill),.3),*pair('备注',native['state'],.35)]
            with self.assertRaises(ValueError):self.validate(top=t,native=n)

    def test_combined_labeled_cell_and_account_number_separate(self):
        self.assertEqual(field([cell('合同编号：69104',.1,.5)],'合同编号'),'69104')
        with self.assertRaises(ValueError):field([cell('1234567890',.1,.5)],'合同编号')

    def test_only_unique_explicit_success_id_is_extracted(self):
        for label in ('合同编号','合同号','委托编号','委托号'):
            self.assertEqual(OrderResult('success','','委托成功 '+label+'：69104').as_dict()['order_id'],'69104')
        for msg,kind in [('已受理 股东账户：1234567890','success'),('已受理 69104','success'),('合同编号：69104 合同编号：69105','success'),('委托号：69104','unknown'),('委托号：69104','error')]:
            self.assertNotIn('order_id',OrderResult(kind,'',msg).as_dict())

    def test_unsupported_platform_fails_closed(self):
        with patch('executor.ocr.platform.system',return_value='Windows'):
            with self.assertRaises(OcrUnavailable):helper_binary()

    def test_complete_native_scan_keeps_every_filled_order_and_never_opens_a_row(self):
        rows=[
            dict(name='甲',code='000001',side='buy',date='2026-11-03',time='10:00:00',price=10,quantity=100,filled=100,state='已成'),
            dict(name='乙',code='000002',side='sell',date='2026-11-03',time='10:01:00',price=20,quantity=200,filled=0,state='已报'),
            dict(name='丙',code='000003',side='sell',date='2026-11-03',time='10:02:00',price=30,quantity=300,filled=100,state='部成')]
        pages={'bottom':[rows[1],rows[2]],'top':[rows[0],rows[1]]}
        class Box:bounds=(0,100,1000,1000)
        class FakeAdb:
            current='bottom'
            def nodes(self):return self.current
            def shell(self,*args):self.current='top' if int(args[3])<int(args[5]) else 'bottom'
            def tap_node(self,*_args):raise AssertionError('不应打开委托行')
        adb=FakeAdb()
        with patch('executor.order_report.OrderBook') as book,patch('executor.order_report.Zhangle.verify_trade_account'),patch('executor.order_report.find_by_id',return_value=Box()),patch('executor.order_report.row_records',side_effect=lambda nodes,_day,_today:[(row,None) for row in pages[nodes]]):
            book.return_value.select.return_value='bottom'
            result=zhangle_filled_orders(adb,'123456','2026-11-03',__import__('datetime').datetime.fromisoformat('2026-11-03T15:10:00+08:00'))
        self.assertTrue(result['complete']);self.assertEqual([(r['code'],r['status'],r['filled']) for r in result['rows']],[('000001','filled',100),('000003','partial',100)])

    def test_unexplained_empty_native_page_is_not_accepted_as_a_complete_empty_cache(self):
        adb=Mock();adb.nodes.return_value=[]
        with patch('executor.order_report.OrderBook') as book,patch('executor.order_report.Zhangle.verify_trade_account'),patch('executor.order_report.row_records',return_value=[]),patch('executor.order_report.is_empty',return_value=False):
            book.return_value.select.return_value=[]
            with self.assertRaisesRegex(ValueError,'没有明确空记录'):
                zhangle_filled_orders(adb,'123456','2026-11-03',__import__('datetime').datetime.fromisoformat('2026-11-03T15:10:00+08:00'))
