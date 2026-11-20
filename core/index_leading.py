"""Display-only index leading line. Never used by signals or order execution.

Eastmoney's own index chart maps trends2 f53 to the index and f58 to its
yellow line (quote.eastmoney.com / emcharts.eastmoney.com). For indices this
is the unweighted leading indicator, not an individual stock's VWAP.
"""
import json
from datetime import datetime
from decimal import Decimal
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from .provider import now_cn, CN

SECIDS={'sh000001':(1,'000001'),'sz399001':(0,'399001'),'sz399006':(0,'399006')}
SLOTS={f'{m//60:02d}:{m%60:02d}' for m in (*range(570,691),*range(781,901))}

def parse_leading(payload,code,now):
 market,ident=SECIDS[code]
 data=payload.get('data') if payload.get('rc')==0 else None
 if not isinstance(data,dict) or data.get('code')!=ident or data.get('market')!=market:
  raise ValueError('领先线指数身份不匹配')
 stamp=datetime.fromtimestamp(data['time'],CN)
 if stamp.timestamp()>now.timestamp()+5:raise ValueError('领先线时间尚未到达')
 base=Decimal(str(data['preClose']))
 if not base.is_finite() or base<=0:raise ValueError('领先线昨收异常')
 day=stamp.date().isoformat();bars=[];last=''
 for raw in data['trends']:
  fields=raw.split(',')
  if len(fields)!=8:raise ValueError('领先线格式异常')
  observed=datetime.strptime(fields[0],'%Y-%m-%d %H:%M').replace(tzinfo=CN)
  time=observed.strftime('%H:%M')
  if observed.date()!=stamp.date() or time<=last or time not in SLOTS:
   raise ValueError('领先线日期或分钟顺序异常')
  last=time
  # The endpoint can include the pending minute. Do not publish it early.
  if observed>min(stamp,now):continue
  weighted=Decimal(fields[2])
  if not weighted.is_finite() or weighted<=0:raise ValueError('领先线配对指数异常')
  try:value=Decimal(fields[7])
  except ArithmeticError:continue
  if value.is_finite() and value>0:bars.append(dict(time=time,close=str(weighted),value=str(value)))
 return dict(code=code,date=day,previous_close=str(base),timestamp=stamp.isoformat(),bars=bars,source='eastmoney')

def leading_minutes(code):
 market,ident=SECIDS[code]
 query=urlencode(dict(secid=f'{market}.{ident}',fields1='f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11',
                      fields2='f51,f52,f53,f54,f55,f56,f57,f58',ndays=1,iscr=0))
 request=Request('https://push2.eastmoney.com/api/qt/stock/trends2/get?'+query,
                 headers={'Referer':'https://quote.eastmoney.com/','User-Agent':'Mozilla/5.0'})
 with urlopen(request,timeout=3) as response:payload=json.load(response)
 return parse_leading(payload,code,now_cn())
