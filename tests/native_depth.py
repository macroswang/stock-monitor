"""Explicitly synthetic, account-free broker depth nodes for isolated tests."""
from dataclasses import replace
from datetime import datetime,timezone
from decimal import Decimal
from executor.adb import Node
from executor.market_price import OPPONENT_POLICY


def selection(side='buy',price='2.01',code='000981',**changes):
 return dict(policy=OPPONENT_POLICY,side=side,code=code,price=price,book_side='ask1' if side=='buy' else 'bid1',source='ths_native_depth',observed_at=datetime.now(timezone.utc).isoformat(),**changes)


def native_depth(broker,mid='2.00',spread='.01'):
 mid=Decimal(mid);spread=Decimal(spread)
 rows=[(f'卖{i}',mid+spread+Decimal('.01')*(i-1)) for i in range(5,0,-1)]+[(f'买{i}',mid-spread-Decimal('.01')*(i-1)) for i in range(1,6)]
 if broker=='ths':
  return [Node('','com.hexin.plat.android:id/five_buy_sale','android.view.View',(850,250,1070,760),False,True,False,False,description=' '.join(format(value,'.2f') for _,value in rows))]
 prefix='com.lphtsccft:id/'
 result=[Node('',prefix+'hq_jy_normal_ai_list','android.widget.ListView',(820,300,1060,900),False,True,False,False)]
 for row,(label,value) in enumerate(rows):
  y=330+row*50
  result += [Node(label,prefix+'hq_jy_normal_ai_label','android.widget.TextView',(840,y,894,y+30),False,True,False,False),Node(format(value,'.2f'),prefix+'hq_jy_normal_ai_price','android.widget.TextView',(894,y,973,y+30),False,True,False,False),Node('6227',prefix+'hq_jy_normal_ai_count','android.widget.TextView',(973,y,1042,y+30),False,True,False,False)]
 return result
