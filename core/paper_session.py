"""Wall-clock gate for simulated trading only; independent of replay timestamps."""
import json
import sys
from datetime import time
from functools import lru_cache
from pathlib import Path
from .provider import CN

@lru_cache(maxsize=4)
def calendar(year):
    root=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent.parent))
    try:
        data=json.loads((root/'fixtures'/f'exchange-calendar-{year}.json').read_text(encoding='utf-8'))
        if data['year']!=year:raise ValueError('calendar year mismatch')
        return data['closed_ranges']
    except (OSError,ValueError,KeyError,TypeError):return None

def trading_error(now):
    now=now.astimezone(CN)
    prefix=f'当前北京时间 {now:%Y-%m-%d %H:%M:%S}：'
    if now.weekday()>=5:return prefix+'周末休市，禁止模拟委托和成交。'
    closed=calendar(now.year)
    if closed is None:return prefix+'尚无该年度已核对的交易日历，禁止模拟委托和成交。'
    day=now.date().isoformat()
    if any(first<=day<=last for first,last in closed):return prefix+'节假日休市，禁止模拟委托和成交。'
    t=now.time()
    if time(14,57)<=t<time(15):return prefix+'收盘集合竞价暂不模拟，禁止模拟委托和成交。'
    if not (time(9,30)<=t<=time(11,30) or time(13)<=t<time(14,57)):
        return prefix+'不在交易时间内，禁止模拟委托和成交。'
    return ''
