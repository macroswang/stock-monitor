"""Read-only Galaxy today-order evidence, including the native ID-less table.

Never tap an order row: it opens a cancellation dialog. The stock name is bound
to its code by the ORIGINAL native submission confirmation, not by a quote or
holdings lookup. This source supplies no broker order number.
"""
import hashlib
import json
import re
from datetime import datetime
from .adb import find_by_id
from .ths_trade import ThsQuery
from .ths_report import verify, number
from .order_report import state, integer


class OrderNotFound(ValueError):pass
class OrderUnavailable(ValueError):pass


def reference(row):
    result={k:row[k] for k in ('date','time','name','side','price','quantity')}
    result['price']=format(number(result['price']).normalize(),'f')
    return result


def order_key(row):
    return hashlib.sha256(json.dumps(reference(row),sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def parse_current(nodes,day):
    container=find_by_id(nodes,'recyclerview_id')
    if not container or not find_by_id(nodes,'today_order_view'):raise OrderUnavailable('不是可读取的当日委托列表')
    labels=('委托时间','委托/均价','委托/成交','状态')
    headers=[]
    for label in labels:
        values=[n for n in nodes if n.text==label and n.bounds[3]<=container.bounds[1]]
        if len(values)!=1:raise OrderUnavailable('当日委托表头无法唯一识别')
        headers.append(values[0])
    edges=[container.bounds[0]]+[n.bounds[0] for n in headers[1:]]+[container.bounds[2]]
    if edges!=sorted(set(edges)):raise ValueError('当日委托列布局无法识别')
    cells=[n for n in nodes if n.text.strip() and 'TextView' in n.class_name and
           container.bounds[1]<=n.bounds[1]<n.bounds[3]<=container.bounds[3] and
           n.resource_id.rsplit('/',1)[-1] not in ('addLog','title')]
    first=[n for n in cells if edges[0]<=n.center[0]<edges[1]]
    clocks=[n for n in first if re.fullmatch(r'(?:(\d{4})-?(\d{2})-?(\d{2})\s+)?\d{2}:\d{2}:\d{2}',n.text.strip())]
    rows=[]
    for clock in clocks:
        above=[n for n in first if n is not clock and n.bounds[3]<=clock.bounds[1]]
        if not above and clock.bounds[1]==container.bounds[1]:continue  # Clipped top row was read on the preceding page.
        if not above:raise ValueError('当日委托行缺少名称')
        name=max(above,key=lambda n:n.bounds[3]);top,bottom=name.bounds[1],clock.bounds[3]
        columns=[sorted([n for n in cells if top<=n.center[1]<=bottom and lo<=n.center[0]<hi],key=lambda n:n.center[1]) for lo,hi in zip(edges,edges[1:])]
        if [len(c) for c in columns]!=[2,2,2,2] or columns[0]!=[name,clock]:
            if bottom==container.bounds[3]:continue  # Read it in full after the next vertical swipe.
            raise ValueError('当日委托行尚未完整显示')
        stamp=clock.text.strip();date=day
        if ' ' in stamp:
            raw,stamp=stamp.split();raw=raw.replace('-','');date=f'{raw[:4]}-{raw[4:6]}-{raw[6:]}'
        if date!=day:raise ValueError('当日委托出现其它交易日期')
        datetime.fromisoformat(day+'T'+stamp)
        price=number(columns[1][0].text);qty=integer(columns[2][0].text);filled=integer(columns[2][1].text)
        side={'买入':'buy','卖出':'sell','撤买':'buy','撤卖':'sell'}.get(columns[3][0].text.strip())
        terminal=state(columns[3][1].text)
        if price<=0 or qty<=0 or filled>qty or not side:raise ValueError('当日委托价格、数量或方向无效')
        if ((terminal in ('accepted','rejected') and filled!=0) or (terminal=='partial' and not 0<filled<qty) or
            (terminal=='filled' and filled!=qty) or (terminal=='cancelled' and filled>=qty)):
            raise ValueError('当日委托状态与成交量不一致')
        row=dict(name=name.text.strip(),date=day,time=stamp,side=side,price=str(price),quantity=qty,filled=filled,status=terminal)
        if filled:
            average=number(columns[1][1].text)
            if average<=0 or (side=='buy' and average>price) or (side=='sell' and average<price):raise ValueError('当日委托成交均价与限价不一致')
            row['average']=str(average)
        rows.append(row)
    if not rows and any(n.resource_id.rsplit('/',1)[-1] not in ('empty_tips',) for n in cells):
        raise ValueError('当日委托行未完整读取')
    return rows


def current_pages(adb,account,day):
    query=ThsQuery(adb);nodes=query.open_home();verify(nodes,adb.current_focus(),account)
    nodes=query._tap_text(nodes,'查询');nodes=query._tap_text(nodes,'当日委托')
    def snapshot():
        ns=adb.nodes();verify(ns,adb.current_focus(),account);return ns
    def scroll(ns,top):
        box=find_by_id(ns,'recyclerview_id')
        if not box:raise ValueError('当日委托列表已离开')
        x=box.center[0];lo,hi=box.bounds[1]+25,box.bounds[3]-25
        adb.shell('input','swipe',str(x),str(lo if top else hi),str(x),str(hi if top else lo),'450')
        return snapshot()
    nodes=snapshot();previous=None
    for _ in range(12):
        rows=parse_current(nodes,day)
        if rows==previous:break
        previous=rows
        if not rows:return
        nodes=scroll(nodes,True)
    else:raise ValueError('无法确认当日委托列表顶部')
    previous=None
    for _ in range(12):
        rows=parse_current(nodes,day)
        if rows==previous:return
        if rows!=parse_current(snapshot(),day):raise ValueError('当日委托读取期间变化，稍后重新核实')
        yield rows
        previous=rows;nodes=scroll(nodes,False)
    raise ValueError('当日委托列表扫描未完成')


def discover_current(adb,account,day,expected,submitted_at,now):
    if day!=now.date().isoformat():raise ValueError('不能从今日委托关联跨日记录')
    submitted=datetime.fromisoformat(submitted_at)
    if submitted.tzinfo is None or submitted.date().isoformat()!=day:raise ValueError('缺少明确的原始提交时间')
    if not expected.get('name'):raise ValueError('缺少原始券商确认中的股票名称')
    records=[]
    for page in current_pages(adb,account,day):
        # RecyclerView pages can overlap. Preserve distinct identical rows;
        # their ambiguity must never be hidden by a dict/set deduplication.
        overlap=max((k for k in range(1,min(len(records),len(page))+1) if records[-k:]==page[:k]),default=0)
        records.extend(page[overlap:])
    matches=[]
    for row in records:
        at=datetime.fromisoformat(day+'T'+row['time']).replace(tzinfo=submitted.tzinfo)
        if (row['name']==expected['name'] and row['side']==expected['side'] and row['quantity']==expected['quantity'] and
            number(row['price'])==number(expected['price']) and -2<=(at-submitted).total_seconds()<=15):matches.append(row)
    if not matches:raise OrderNotFound('当日委托中没有与原始确认一致的记录')
    if len(matches)!=1:raise ValueError('当日委托存在多个相同候选，不能唯一关联')
    row=dict(matches[0],found=True,kind='native_order',code=expected['code'],order_id='',source='ths_native_today_order',
             date_source='broker_today_query',receipt_recovery=dict(submitted_at=submitted_at,method='native_order_list'))
    row['native_order_key']=order_key(row)
    row['evidence_hash']=hashlib.sha256(json.dumps(row,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    return row
