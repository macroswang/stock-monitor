"""Account-stock order sizing. No monetary quota is applied here."""
from fractions import Fraction

BUY_CASH_RESERVE_RATE = .003
BUY_CASH_RESERVE_FIXED = 5


def buy_cash_required(value):
    return value*(1+BUY_CASH_RESERVE_RATE)+BUY_CASH_RESERVE_FIXED


def order_quantity(code,base,fraction,side):
    raw=int(Fraction(str(base))*Fraction(str(fraction)))
    if code.startswith('sh688'):
        return raw if raw>=200 or (side=='sell' and raw==base) else 0
    if side=='sell' and raw==base:return raw
    return raw//100*100


def quantity(code,position,sellable,side,rule):
    mode=rule[side+'_mode']
    if mode=='lots':
        raw=rule[side+'_lots']*100
        if side=='sell' and raw>sellable:raise ValueError(f'当前可卖{sellable}股，不足设定的{rule[side+"_lots"]}手')
        return order_quantity(code,raw,'1','buy')
    if mode!='position':raise ValueError('请选择固定手数或当前持仓百分比')
    raw=int(Fraction(position)*Fraction(str(rule[side+'_percent']))/100)
    if side=='sell':
        raw=min(raw,sellable)
        if raw==sellable:return raw
    return order_quantity(code,raw,'1','buy')


def migrate_rule(code,old,position,defaults):
    """Preserve switches and prior intended whole lots; discard old money quotas."""
    new={k:old.get(k,v) for k,v in defaults.items()}
    for side in ('buy','sell'):
        if side+'_mode' in old:continue
        base=old.get('base_shares',position.get('quantity',0)) if side=='buy' else position.get('sellable',0)
        count=order_quantity(code,base,old.get(side+'_ratio','1/2'),side)
        new[side+'_mode']='lots'
        new[side+'_lots']=max(2 if code.startswith('sh688') else 1,count//100)
    return new
