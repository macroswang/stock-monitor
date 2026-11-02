import unittest
from unittest.mock import patch
from executor.adb import Node
from executor.ths_report import parse_group,merge_groups,anchor,verify


def n(text,rid='',x=0,y=0,w=200,h=40):
 return Node(text,'com.hexin.plat.android:id/'+rid if rid else '','android.widget.TextView',(x,y,x+w,y+h),False,True,False,False)

def screen(right=False,contract='T001',code='603938',clock='13:57:00',qty='200',average='29.410',money='5882.000'):
 headers=[n('合同编号',x=540,y=300),n('股票代码',x=800,y=300)] if right else [n('成交均价',x=280,y=300),n('成交量',x=540,y=300)]
 fields=[n(contract,'contract',540,420),n(code,'stock_code',800,420)] if right else [n(average,'price',280,420),n(qty,'amount',540,420)]
 return [n('','recyclerview_id',0,385,1080,1430),*headers,n('三孚股份','stock_name',32,405),n(clock,'deal_time',66,443),n('卖出','opt_type',818 if not right else 310,405),n(money,'deal_money',818 if not right else 310,443),*fields]

class NativeContractTests(unittest.TestCase):
 def setUp(self):
  self.day='2026-11-02';self.left=parse_group(screen(),self.day);self.right=parse_group(screen(True),self.day,True)
 def test_native_contract_and_code_join_to_cumulative_quantity_and_average(self):
  result=merge_groups(self.left,self.right,self.right,self.left)[0]
  self.assertEqual((result['order_id'],result['code'],result['filled'],result['average']),('T001','603938',200,'29.410'))
 def test_contract_id_cannot_be_guessed_from_name_or_numeric_column(self):
  for changes in [dict(contract=''),dict(code='123'),dict(contract='bad id')]:
   with self.subTest(changes=changes),self.assertRaises(ValueError):parse_group(screen(True,**changes),self.day,True)
  with self.assertRaises(ValueError):parse_group(screen(),self.day,True)
 def test_missing_fields_wrong_mode_duplicate_fields_rejected(self):
  for nodes in [screen()[:-1],screen()[1:],screen()+[n('200','amount',540,460)], [v for v in screen() if v.text!='成交均价']]:
   with self.assertRaises(ValueError):parse_group(nodes,self.day)
 def test_changed_contract_code_fill_or_row_between_reads_never_updates(self):
  for altered in [parse_group(screen(True,contract='T002'),self.day,True),parse_group(screen(True,code='000981'),self.day,True)]:
   with self.assertRaises(ValueError):merge_groups(self.left,self.right,altered,self.left)
  with self.assertRaises(ValueError):merge_groups(self.left,self.right,self.right,parse_group(screen(qty='201'),self.day))
  with self.assertRaises(ValueError):merge_groups(self.left,parse_group(screen(True,clock='13:57:01'),self.day,True),parse_group(screen(True,clock='13:57:01'),self.day,True),self.left)
 def test_ambiguous_identical_anchors_or_duplicate_contracts_rejected(self):
  with self.assertRaises(ValueError):merge_groups(self.left*2,self.right*2,self.right*2,self.left*2)
  second_l=parse_group(screen(clock='13:58:00'),self.day);second_r=parse_group(screen(True,clock='13:58:00'),self.day,True)
  with self.assertRaises(ValueError):merge_groups(self.left+second_l,self.right+second_r,self.right+second_r,self.left+second_l)
 def test_noninteger_quantity_nan_wrong_direction_or_date_rejected(self):
  for change in [dict(qty='1.5'),dict(qty='0'),dict(average='NaN'),dict(money='-1'),dict(clock='20261101 13:57:00')]:
   with self.subTest(change=change),self.assertRaises(ValueError):parse_group(screen(**change),self.day)
 def test_read_does_not_treat_shareholder_code_as_capital_account(self):
  ns=[n('中国银河证券','page_title_view'),n('**0162','account_info_view')]
  verify(ns,'com.hexin.plat.android','400401000162')
  for account,focus in [('400401999999','com.hexin.plat.android'),('400401000162','other.app')]:
   with self.assertRaises(ValueError):verify(ns,focus,account)

class ContractNavigationTests(unittest.TestCase):
 def test_persisted_contract_mode_is_not_clicked_again(self):
  from unittest.mock import Mock,patch
  from executor.ths_report import open_contract_groups
  adb=Mock();adb.nodes.return_value=screen();adb.current_focus.return_value='com.hexin.plat.android'
  query=Mock();query.open_home.return_value=[];query._tap_text.return_value=[]
  with patch('executor.ths_report.ThsQuery',return_value=query),patch('executor.ths_report.verify'):
   open_contract_groups(adb,'1234567')
  self.assertEqual([call.args[1] for call in query._tap_text.call_args_list],['查询','当日委托','当日成交'])
  adb.tap_node.assert_not_called()
 def test_unselected_contract_mode_is_clicked_once_then_checked(self):
  from unittest.mock import Mock,patch
  from executor.ths_report import open_contract_groups
  adb=Mock();adb.nodes.side_effect=[[n('按合同编号','tip_textview',540,245)],screen()];adb.current_focus.return_value='com.hexin.plat.android'
  with patch('executor.ths_report.ThsQuery'),patch('executor.ths_report.verify') as checked:
   result=open_contract_groups(adb,'1234567')
  adb.tap_node.assert_called_once();self.assertTrue(result);self.assertEqual(checked.call_count,3)
