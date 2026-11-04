"""Validate optional direction-aware index volume without inferring trade sides.

The current public index feed supplies totals only. A direction-aware source
must explicitly identify its index/date/minute, lot unit, full index coverage,
trade-initiator basis and completed quantities before its split can be drawn.
"""
from datetime import date

MAX_SAFE=9007199254740991
FIELDS=('buy_lots','sell_lots','neutral_lots','unknown_lots')
TIMES={f'{m//60:02}:{m%60:02}' for m in (*range(570,691),*range(781,901))}

def valid_lots(value):
    return type(value) is int and 0<=value<=MAX_SAFE

def index_direction(code,day,bar):
    raw=bar.get('volume_direction')
    if not isinstance(raw,dict) or not valid_lots(bar.get('volume_lots')) or bar.get('time') not in TIMES:return None
    try:date.fromisoformat(day)
    except (ValueError,TypeError):return None
    if (raw.get('code')!=code or raw.get('day')!=day or raw.get('time')!=bar.get('time') or
        raw.get('unit')!='lots' or raw.get('scope')!='index_total' or raw.get('basis')!='trade_initiator' or
        raw.get('complete') is not True or not isinstance(raw.get('source'),str) or not raw['source'].strip()):return None
    quantities=[raw.get(k) for k in FIELDS]
    total=bar['volume_lots']
    if not all(valid_lots(v) for v in quantities) or not valid_lots(raw.get('total_lots')) or raw['total_lots']!=total or sum(quantities)!=total:return None
    return dict(code=code,day=day,time=bar['time'],unit='lots',scope='index_total',basis='trade_initiator',
        complete=True,source=raw['source'],total_lots=total,**dict(zip(FIELDS,quantities)))

def normalize_index_minute(group,code):
    bars=[];verified=0;eligible=0
    for original in group.get('bars',[]):
        bar=dict(original);raw=index_direction(code,group.get('date'),bar)
        bar.pop('volume_direction',None)
        if valid_lots(bar.get('volume_lots')):eligible+=1
        if raw:bar['volume_direction']=raw;verified+=1
        bars.append(bar)
    return dict(group,code=code,bars=bars,direction_status='complete' if eligible and verified==eligible else 'partial' if verified else 'unavailable')
