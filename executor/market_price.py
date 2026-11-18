"""Native broker depth selection. No order buttons, cancellations or retries here."""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import re

OPPONENT_POLICY = 'broker-opponent-best-v1'


class MarketPriceError(ValueError):
    pass


def price_number(value):
    text=str(value).strip()
    if not re.fullmatch(r'\d+(?:\.\d{1,3})?',text):raise MarketPriceError('盘口价格无效')
    try:number=Decimal(text)
    except InvalidOperation:raise MarketPriceError('盘口价格无效') from None
    if not number.is_finite() or number<=0 or number!=number.quantize(Decimal('.01')):
        raise MarketPriceError('盘口价格不是有效的股票最小报价单位')
    return number


def depth_price(nodes, broker, side):
    if side not in ('buy','sell'):raise MarketPriceError('盘口买卖方向无效')
    if broker=='ths':
        books=[n for n in nodes if n.resource_id=='com.hexin.plat.android:id/five_buy_sale' and n.enabled]
        if len(books)!=1:raise MarketPriceError('无法唯一读取券商五档盘口')
        tokens=books[0].description.split()
        if len(tokens)!=10:raise MarketPriceError('券商五档报价不完整，禁止猜测买一或卖一')
        values=[None if t in ('--','—','-') else price_number(t) for t in tokens]
        asks,bids=values[:5],values[5:]
    elif broker=='zhangle':
        asks,bids=zhangle_depth(nodes)
    else:raise MarketPriceError('该券商尚未核验对手价盘口')
    for row in (asks,bids):
        known=[n for n in row if n is not None]
        if any(a<b for a,b in zip(known,known[1:])):raise MarketPriceError('券商五档报价顺序异常')
    if asks[-1] is not None and bids[0] is not None and asks[-1]<bids[0]:
        raise MarketPriceError('券商买卖盘口交叉，暂不发送委托')
    price=asks[-1] if side=='buy' else bids[0]
    if price is None:raise MarketPriceError('对手一档没有有效报价，未发送委托')
    return format(price,'.2f')


def zhangle_depth(nodes):
    prefix='com.lphtsccft:id/'
    books=[n for n in nodes if n.resource_id==prefix+'hq_jy_normal_ai_list' and n.enabled]
    if len(books)!=1:raise MarketPriceError('无法唯一读取华泰五档盘口')
    box=books[0].bounds
    inside=lambda n:box[0]<=n.center[0]<=box[2] and box[1]<=n.center[1]<=box[3]
    scoped=[n for n in nodes if inside(n)]
    def level(side,index):
        labels=[n for n in scoped if n.resource_id==prefix+'hq_jy_normal_ai_label' and n.text.strip()==side+str(index)]
        if len(labels)!=1:raise MarketPriceError('华泰盘口档位无法唯一识别')
        label=labels[0]
        prices=[n for n in scoped if n.resource_id==prefix+'hq_jy_normal_ai_price' and n.bounds[0]>=label.bounds[2] and label.bounds[1]<=n.center[1]<=label.bounds[3]]
        if len(prices)!=1:raise MarketPriceError('华泰盘口价格与档位不能唯一对应')
        text=prices[0].text.strip()
        return None if text in ('--','—','-') else price_number(text)
    return [level('卖',i) for i in range(5,0,-1)],[level('买',i) for i in range(1,6)]


def validate_selection(selection,code,side,now=None):
    if not isinstance(selection,dict) or selection.get('policy')!=OPPONENT_POLICY or selection.get('code')!=code or selection.get('side')!=side or selection.get('book_side')!=('ask1' if side=='buy' else 'bid1'):
        raise MarketPriceError('盘口证据与委托股票或方向不一致')
    stamp=datetime.fromisoformat(selection.get('observed_at',''))
    if stamp.tzinfo is None:raise MarketPriceError('盘口读取时间缺少时区')
    age=((now or datetime.now(timezone.utc))-stamp).total_seconds()
    if not 0<=age<=5:raise MarketPriceError('盘口读取已过期，未发送委托')
    return format(price_number(selection.get('price')),'.2f')


def prepare_opponent(broker,side,code,quantity,snapshot,read_form,fill,*,nodes=None):
    """Select one verified opponent price and check that the form retains it."""
    nodes=snapshot() if nodes is None else nodes
    form=read_form(nodes)
    expected=(side,code,str(quantity))
    if not form or (form.side,form.code,form.quantity)!=expected:
        raise MarketPriceError('读取盘口时委托股票、方向或数量已变化')
    chosen=depth_price(nodes,broker,side)
    observed_at=datetime.now(timezone.utc).isoformat()
    if not form.price or price_number(form.price)!=price_number(chosen):
        fill(0,chosen,nodes=nodes)
        nodes=snapshot()
        form=read_form(nodes)
        if not form or (form.side,form.code,form.quantity)!=expected:
            raise MarketPriceError('填价后委托表单已变化')
        if not form.price or price_number(form.price)!=price_number(chosen):
            raise MarketPriceError('表单价格与已选对手价不一致，未发送委托')
    evidence=dict(policy=OPPONENT_POLICY,code=code,side=side,book_side='ask1' if side=='buy' else 'bid1',price=chosen,
                  source=broker+'_native_depth',observed_at=observed_at)
    return form,nodes,evidence
