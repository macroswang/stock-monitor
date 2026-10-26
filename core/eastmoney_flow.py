"""Bounded public Eastmoney supplement; independently dated and checked per minute."""
import json
import re
from datetime import datetime,time as clock_time
from decimal import Decimal
from urllib.parse import urlencode
from urllib.request import Request,urlopen
from .provider import CN,now_cn,symbol


def parse_details(payload,code):
    data=payload.get('data') or {}
    if str(data.get('code'))!=code[2:] or int(data.get('market',-1))!=(1 if code.startswith('sh') else 0):raise ValueError('东财返回代码不一致')
    rows=data.get('details')
    if not isinstance(rows,list) or not rows:raise ValueError('东财无成交明细')
    parsed=[];buckets={};last=''
    for row in rows:
        parts=row.split(',')
        if len(parts)!=5:raise ValueError('东财明细字段不足')
        stamp,price,volume,_,direction=parts
        if not re.fullmatch(r'\d{2}:\d{2}:\d{2}',stamp):raise ValueError('东财明细时间格式无效')
        clock_time.fromisoformat(stamp)
        if stamp<last:raise ValueError('东财明细时间倒退')
        p,v=Decimal(price),Decimal(volume)*100
        if not p.is_finite() or p<=0 or not v.is_finite() or v<0 or v!=int(v):raise ValueError('东财明细价格或单位无效')
        last=stamp;parsed.append(dict(time=stamp,price=str(p),shares=int(v),direction=direction))
        if not ('09:30:00'<=stamp<='11:30:00' or '13:00:00'<=stamp<'14:57:00'):continue
        h,m,_=map(int,stamp.split(':'));n=690 if stamp=='11:30:00' else h*60+m+1;label=f'{n//60:02}:{n%60:02}'
        bucket=buckets.setdefault(label,dict(buy=0,sell=0,neutral=0,unknown=0,total=0,last_price=str(p)))
        field={'2':'buy','1':'sell','4':'neutral'}.get(direction,'unknown')
        bucket[field]+=int(v);bucket['total']+=int(v);bucket['last_price']=str(p)
    continuous=[r for r in parsed if '09:30:00'<=r['time']<='11:30:00' or '13:00:00'<=r['time']<'14:57:00']
    return dict(rows=len(rows),last_trade=continuous[-1]['time'] if continuous else None,buckets=buckets,raw=payload)


class EastmoneyTicks:
    """No retries in a request. Network work always runs in VolumeFlow's worker."""
    def __init__(self,reader=None):self.reader=reader

    def get(self,code,kind):
        secid=f"{1 if code.startswith('sh') else 0}.{code[2:]}"
        if kind=='quote':
            url='https://push2.eastmoney.com/api/qt/stock/get?'+urlencode(dict(secid=secid,fields='f57,f86',fltt='2'))
        else:
            url='https://70.push2.eastmoney.com/api/qt/stock/details/sse?'+urlencode(dict(fields1='f1,f2,f3,f4',fields2='f51,f52,f53,f54,f55',mpi='2000',ut='bd1d9ddb04089700cf9c27f6f7426281',fltt='2',pos='-0',secid=secid,wbp2u='|0|0|0|web'))
        if self.reader:return self.reader(url)
        with urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0','Referer':'https://quote.eastmoney.com/'}),timeout=6) as response:
            if kind=='quote':
                data=response.read(2*1024*1024+1)
                if len(data)>2*1024*1024:raise ValueError('东财响应过大')
                return json.loads(data)
            size=0
            for _ in range(16):
                line=response.readline(2*1024*1024+1);size+=len(line)
                if size>2*1024*1024:raise ValueError('东财响应过大')
                if line.startswith(b'data:'):return json.loads(line[5:])
        raise ValueError('未取得东财首个数据事件')

    def quote_date(self,code,day):
        data=self.get(code,'quote').get('data') or {}
        if data.get('f57')!=code[2:] or not isinstance(data.get('f86'),(int,float)):raise ValueError('东财报价缺少可核验日期')
        stamp=datetime.fromtimestamp(data['f86'],CN)
        if stamp.date().isoformat()!=day:raise ValueError('东财分笔交易日与所选日期不一致')
        now=now_cn()
        if stamp>now:raise ValueError('东财报价时间超前')
        if day==now.date().isoformat() and ('09:30'<=now.strftime('%H:%M')<='11:30' or '13:00'<=now.strftime('%H:%M')<'14:57') and (now-stamp).total_seconds()>90:raise ValueError('东财当日报价未及时更新')
        return stamp.isoformat()

    def fetch(self,code,day,reference):
        code=symbol(code)
        before=self.quote_date(code,day)
        snapshot=parse_details(self.get(code,'details'),code)
        after=self.quote_date(code,day)
        # Never combine quantities across providers. Only whole minutes with an
        # exact authoritative volume AND closing-price match are eligible.
        buckets={}
        for bar in reference.get('bars',[]):
            row=snapshot['buckets'].get(bar['time'])
            if row and bar.get('complete') and bar['volume']>0 and row['total']==bar['volume'] and Decimal(row['last_price'])==Decimal(bar['close']):buckets[bar['time']]=row
        return dict(version=1,code=code,day=day,source='eastmoney_tick',date_verified=True,quote_before=before,quote_after=after,fetched_at=now_cn().isoformat(),last_tick=snapshot['last_trade'],record_count=snapshot['rows'],buckets=buckets)
