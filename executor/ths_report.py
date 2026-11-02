"""Read-only native THS/Galaxy contract-group execution reports.

The default list hides identity columns. Select today's contract aggregation,
then swipe ON a populated row. Never open a row: that opens a cancellation UI.
"""
import hashlib
import json
import re
from decimal import Decimal,InvalidOperation
from .adb import find_by_id,find_by_text
from .ths import read_status,PACKAGE
from .ths_trade import ThsQuery
from .identity import account_matches


def number(value):
    try:
        n=Decimal(str(value).replace(',',''))
        if not n.is_finite() or n<0:raise ValueError()
        return n
    except (InvalidOperation,ValueError):raise ValueError('合同成交数值不完整') from None


def verify(nodes,focus,account):
    s=read_status(nodes,focus)
    if not account or not s.app_foreground or '银河' not in s.broker_name or not account_matches(s.account_masked,account):
        raise ValueError('读取合同回报期间证券账户变化，已停止')


def parse_group(nodes,day,right=False):
    container=find_by_id(nodes,'recyclerview_id')
    if not container:raise ValueError('合同成交列表未就绪')
    labels={n.text for n in nodes if n.bounds[3]<=container.bounds[1]}
    required={'合同编号','股票代码'} if right else {'成交均价','成交量'}
    if not required<=labels:raise ValueError('不是按合同编号汇总的成交查询页')
    keys={'stock_name','deal_time','opt_type','deal_money','contract','stock_code'} if right else {'stock_name','deal_time','opt_type','deal_money','price','amount'}
    rows=[];row=None
    for n in nodes:
        if not container.bounds[1]<=n.center[1]<=container.bounds[3]:continue
        rid=n.resource_id.rsplit('/',1)[-1]
        if rid=='stock_name':
            row={};rows.append(row)
        if row is not None and rid in keys:
            if rid in row:raise ValueError('合同成交行字段重复')
            row[rid]=n.text.strip()
    result=[]
    for row in rows:
        if set(row)!=keys:raise ValueError('合同成交行尚未完整显示')
        stamp=row['deal_time'];m=re.fullmatch(r'(?:(\d{4})-?(\d{2})-?(\d{2})\s+)?(\d{2}:\d{2}:\d{2})',stamp)
        if not m:raise ValueError('合同成交时间不完整')
        date='-'.join(m.group(1,2,3)) if m.group(1) else day
        if date!=day:raise ValueError('合同成交日期与查询日期不一致')
        side={'买入':'buy','卖出':'sell'}.get(row['opt_type'])
        if not side:raise ValueError('合同成交方向无法识别')
        item=dict(name=row['stock_name'],date=date,time=m.group(4),side=side,amount=str(number(row['deal_money'])))
        if right:
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',row['contract']) or not re.fullmatch(r'\d{6}',row['stock_code']):
                raise ValueError('合同编号或股票代码不完整')
            item.update(order_id=row['contract'],code=row['stock_code'])
        else:
            qty=number(row['amount']);average=number(row['price'])
            if qty!=int(qty) or qty<=0 or average<=0:raise ValueError('合同累计成交量或均价无效')
            item.update(filled=int(qty),average=str(average))
        result.append(item)
    return result


def anchor(row):return tuple(row[k] for k in ('name','date','time','side','amount'))


def open_contract_groups(adb,account):
    q=ThsQuery(adb);nodes=q.open_home()
    verify(nodes,adb.current_focus(),account)
    nodes=q._tap_text(nodes,'查询')
    # Enter a native query first, then its today-deal tab. The legacy home-menu
    # shortcut can produce a blank page in this installed THS build.
    nodes=q._tap_text(nodes,'当日委托');nodes=q._tap_text(nodes,'当日成交')
    nodes=adb.nodes();verify(nodes,adb.current_focus(),account)
    # Group selection persists across visits. Re-tapping its selected label can
    # open an empty page; use the rendered named schema to recognize it instead.
    if not find_by_id(nodes,'price') or not any(n.text=='成交均价' for n in nodes):
        button=find_by_text(nodes,'按合同编号')
        if not button:raise ValueError('当前页面没有按合同编号查询入口')
        adb.tap_node(button);nodes=adb.nodes();verify(nodes,adb.current_focus(),account)
    return nodes


def merge_groups(left,right,second_right,second_left):
    if left!=second_left or right!=second_right:raise ValueError('合同成交回报读取期间变化，稍后重新核实')
    def unique(rows):
        mapped={anchor(r):r for r in rows}
        if len(mapped)!=len(rows):raise ValueError('合同成交行无法唯一对应，保留待核实')
        return mapped
    l,r=unique(left),unique(right)
    if l.keys()!=r.keys():raise ValueError('滑动期间合同成交行发生变化')
    records=[dict(l[k],**r[k]) for k in l]
    if len({v['order_id'] for v in records})!=len(records):raise ValueError('合同汇总出现重复编号')
    return records


def report(adb,account,order_id,day,expected,now):
    if day!=now.date().isoformat():raise ValueError('当前银河合同汇总只支持当日回报；跨日委托保留待核实')
    nodes=open_contract_groups(adb,account)
    def snapshot():
        ns=adb.nodes();verify(ns,adb.current_focus(),account);return ns
    def horizontal(ns,right):
        name=find_by_id(ns,'stock_name')
        if not name:raise ValueError('没有可读取的合同成交记录，仍待核实')
        width,_=adb.display_size();y=name.center[1]
        adb.shell('input','swipe',str(int(width*.94) if right else int(width*.3)),str(y),str(int(width*.12) if right else int(width*.97)),str(y),'500')
        return snapshot()
    def vertical(ns,down):
        c=find_by_id(ns,'recyclerview_id')
        if not c:raise ValueError('合同成交列表已离开')
        x=(c.bounds[0]+c.bounds[2])//2;top=c.bounds[1]+25;bottom=c.bounds[3]-25
        adb.shell('input','swipe',str(x),str(top if down else bottom),str(x),str(bottom if down else top),'450')
        return snapshot()
    nodes=snapshot()
    # Reset the horizontal position using a real row, never empty screen space.
    if not find_by_id(nodes,'price'):nodes=horizontal(nodes,False)
    previous=None
    for _ in range(12):
        rows=parse_group(nodes,day);current=tuple(anchor(r) for r in rows)
        if current==previous:break
        previous=current;nodes=vertical(nodes,True)
    else:raise ValueError('无法确认合同成交列表顶部')
    seen=set()
    for _ in range(12):
        left=parse_group(nodes,day)
        key=tuple(anchor(r) for r in left)
        if key in seen:break
        seen.add(key)
        right_nodes=horizontal(nodes,True);right=parse_group(right_nodes,day,True)
        second_right=parse_group(snapshot(),day,True)
        nodes=horizontal(right_nodes,False);second_left=parse_group(nodes,day)
        records=merge_groups(left,right,second_right,second_left)
        matches=[r for r in records if r['order_id']==order_id]
        if matches:
            row=matches[0]
            if row['code']!=expected['code'] or row['side']!=expected['side']:raise ValueError('合同编号对应的股票或方向不符')
            row.update(found=True,kind='contract_fills',source='ths_native_contract_group',date_source='broker_today_query')
            row['evidence_hash']=hashlib.sha256(json.dumps(row,sort_keys=True).encode()).hexdigest()
            return row
        nodes=vertical(nodes,False)
    return dict(found=False,message='本次合同成交列表未找到该编号；不认定未提交或已撤单')
