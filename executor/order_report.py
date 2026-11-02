"""Read-only order evidence, cross-checking a native row against its web detail.

OCR alone cannot settle an order: code, direction, time, price, quantity, filled
quantity and state must agree with the native broker row, and the requested
contract ID must be read identically from two fresh screenshots.
"""
import hashlib
import json
import re
from dataclasses import replace
from decimal import Decimal,InvalidOperation
from .adb import find_by_id,wait_until
from .ocr import recognize,helper_binary
from .orderbook import OrderBook,_rows,_scoped,parse_rows,ROW_ID,NAME_ID,RECYCLER_ID
from .zhangle import Zhangle,PACKAGE


def normalized(text):return re.sub(r'\s+','',str(text)).replace('（','(').replace('）',')').replace('，',',').replace('：',':')


class ContractMismatch(ValueError):pass


def decimal(value):
    try:
        result=Decimal(str(value).replace(',',''))
        if not result.is_finite():raise ValueError()
        return result
    except (InvalidOperation,ValueError):raise ValueError('委托明细数值无法核验') from None


def integer(value):
    result=decimal(value)
    if result<0 or result!=int(result):raise ValueError('委托数量无法核验')
    return int(result)


def field(rows,label):
    """Only a named, high-confidence cell or its unique value on the same row."""
    values=[]
    for cell in rows:
        if cell.get('confidence',0)<.99:continue
        text=normalized(cell.get('text',''))
        if text.startswith(label) and len(text)>len(label):
            suffix=text[len(label):].lstrip(':')
            if suffix:values.append(suffix)
        if text!=label:continue
        cy=cell['y']+cell['height']/2
        for value in rows:
            if value is cell or value.get('confidence',0)<.99 or value['x']<=cell['x']+cell['width']*.8:continue
            if abs(value['y']+value['height']/2-cy)<=max(cell['height'],value['height'])*.7:
                values.append(normalized(value['text']))
    values=set(values)
    if len(values)!=1:raise ValueError('委托明细字段不完整或不唯一：'+label)
    return values.pop()


STATES={'已成':'filled','已成交':'filled','全部成交':'filled','部成':'partial','部分成交':'partial',
        '已报':'accepted','未报':'accepted','待报':'accepted','已报待撤':'accepted',
        '已撤':'cancelled','部撤':'cancelled','已拒绝':'rejected','废单':'rejected'}


def state(value):
    text=normalized(value)
    prefix=re.sub(r'\([^)]*\)$','',text)
    if prefix not in STATES:raise ValueError('券商委托状态尚未识别：'+prefix)
    return STATES[prefix]


def validate_frames(top,bottom,second_bottom,native,order_id,day):
    texts=[normalized(c['text']) for c in top if c.get('confidence',0)>=.99]
    if '委托明细' not in texts or native['code'] not in texts or ('买入' if native['side']=='buy' else '卖出') not in texts:
        raise ValueError('网页委托的股票或方向与原生记录不符')
    if native.get('time') not in texts:raise ValueError('网页委托时间与原生记录不符')
    if native.get('date')!=day:raise ValueError('委托交易日期不符')
    quantity=integer(field(top,'委托数量'));price=decimal(field(top,'委托价格'))
    filled=integer(field(top,'成交数量'))
    if quantity!=integer(native.get('quantity')) or price!=decimal(native.get('price')) or filled!=integer(native.get('filled')):
        raise ValueError('网页委托价格、数量或成交数量与原生记录不符')
    terminal=state(field(top,'备注'))
    if terminal!=state(native.get('state','')):raise ValueError('网页委托状态与原生记录不符')
    first_id=field(bottom,'合同编号');second_id=field(second_bottom,'合同编号')
    if not re.fullmatch(r'\d{1,20}',first_id) or first_id!=second_id:
        raise ValueError('合同编号未与目标编号一致核验')
    if first_id!=str(order_id):raise ContractMismatch('本行不是目标合同编号')
    if filled>quantity or (terminal=='filled' and filled!=quantity) or (terminal=='rejected' and filled!=0):
        raise ValueError('成交数量与终态不符')
    payload=dict(order_id=first_id,date=day,time=native['time'],code=native['code'],name=native['name'],side=native['side'],
                 quantity=quantity,price=str(price),filled=filled,status=terminal,broker_state=native['state'])
    payload['evidence_hash']=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
    return payload


def row_records(nodes,day,today):
    records=[]
    for raw in _rows(_scoped(nodes,RECYCLER_ID) or nodes):
        name=raw.get(NAME_ID)
        if not name:continue
        values=parse_rows([replace(name,resource_id=ROW_ID,text=''),*raw.values()],'order')
        if not values:continue
        row=values[0].as_dict()
        if not row.get('date') and today:row.update(date=day,date_source='broker_today_query')
        records.append((row,name))
    return records


def signature(row):return tuple(row.get(k) for k in ('code','side','date','time','price','quantity','filled','state'))


def inspect_detail(adb,node,native,order_id,day,account):
    adb.tap_node(node)
    try:
        def loaded():
            if PACKAGE not in adb.current_focus():raise ValueError('读取明细时已离开目标券商')
            rows=recognize(adb)
            try:
                # Wait for the actual page body, not just its loading title.
                field(rows,'委托价格');field(rows,'委托数量');field(rows,'成交数量');field(rows,'备注')
                return rows
            except ValueError:return None
        top=wait_until(loaded,timeout=25,interval=.3)
        if not top:raise ValueError('委托明细未加载完整，保留待核实状态')
        bottom=None
        for _ in range(5):
            rows=recognize(adb)
            try:field(rows,'合同编号');bottom=rows;break
            except ValueError:
                width,height=adb.display_size()
                adb.shell('input','swipe',str(width//2),str(int(height*.8)),str(width//2),str(int(height*.25)),'500')
        if bottom is None:raise ValueError('未读取到合同编号，保留待核实状态')
        second=recognize(adb)
        return validate_frames(top,bottom,second,native,order_id,day)
    finally:
        adb.keyevent(4)
        nodes=adb.nodes()
        Zhangle.verify_trade_account(nodes,account)


def zhangle_report(adb,account,order_id,day,expected,now):
    helper_binary()  # Unsupported builds fail before opening a detail page.
    if not re.fullmatch(r'\d{1,20}',str(order_id)):raise ValueError('目标合同编号格式无效')
    if not account:raise ValueError('缺少已核验的资金账户')
    today=day==now.date().isoformat();key='today_orders' if today else 'history_orders'
    book=OrderBook(adb);nodes=book.select(key);seen=set()
    for _ in range(15):
        Zhangle.verify_trade_account(nodes,account)
        before=tuple(signature(r)[:6] for r,_ in row_records(nodes,day,today))
        container=find_by_id(nodes,RECYCLER_ID)
        if not container:break
        x1,y1,x2,y2=container.bounds
        adb.shell('input','swipe',str((x1+x2)//2),str(y1+25),str((x1+x2)//2),str(y2-25),'500')
        nodes=adb.nodes()
        if tuple(signature(r)[:6] for r,_ in row_records(nodes,day,today))==before:break
    else:raise ValueError('未能确认委托列表顶部，保留待核实状态')
    for _ in range(15):
        Zhangle.verify_trade_account(nodes,account)
        records=row_records(nodes,day,today)
        page_signature=tuple(signature(r) for r,_ in records)
        if page_signature in seen:break
        seen.add(page_signature)
        for row,node in records:
            if row['code']!=expected['code'] or row['side']!=expected['side'] or row['date']!=day:continue
            try:
                if integer(row.get('quantity'))!=expected['quantity'] or decimal(row.get('price'))!=decimal(expected['price']):continue
            except ValueError:continue
            # Re-derive the clickable row after returning from another detail.
            current=next(((r,n) for r,n in row_records(nodes,day,today) if signature(r)==signature(row)),None)
            if current is None:raise ValueError('委托列表变化，稍后重新核验')
            row,node=current
            try:result=inspect_detail(adb,node,row,order_id,day,account)
            except ContractMismatch:
                nodes=book.select(key)
                continue
            restored=book.select(key)
            if not any(signature(r)==signature(row) for r,_ in row_records(restored,day,today)):
                raise ValueError('读取期间原生委托状态变化，稍后重新核验')
            return dict(found=True,**result,source='broker_native_and_local_vision',date_source=row.get('date_source','broker_row'))
        container=find_by_id(nodes,RECYCLER_ID)
        if not container:break
        x1,y1,x2,y2=container.bounds
        adb.shell('input','swipe',str((x1+x2)//2),str(y2-25),str((x1+x2)//2),str(y1+25),'500')
        nodes=adb.nodes()
    return dict(found=False,message='本次可读范围内没有一致的合同编号；不能据此认定未提交')
