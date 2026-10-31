"""新浪板块成分只读匹配；来源未提供成分生效日期。"""
import json
import re
import threading
import time
from urllib.parse import urlencode
from .provider import get,now_cn

BASE='https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.'


def fetch(code):
 if not isinstance(code,str) or not re.fullmatch(r'(?:new_|gn_)[A-Za-z0-9]+',code):raise ValueError('不支持的新浪板块代码')
 params={'node':code,'page':1,'num':1000,'sort':'symbol','asc':1}
 def read(method):return json.loads(get(BASE+method+'?'+urlencode(params)))
 count=int(read('getHQNodeStockCount'));rows=read('getHQNodeData');final=int(read('getHQNodeStockCount'))
 if count!=final or count<1 or count>1000 or not isinstance(rows,list) or len(rows)!=count:raise ValueError('板块成分数量不完整')
 members=[];seen=set()
 for row in rows:
  symbol=row.get('symbol');name=row.get('name')
  if not isinstance(symbol,str) or not re.fullmatch(r'(?:sh|sz|bj)\d{6}',symbol) or symbol in seen or not isinstance(name,str) or not name:raise ValueError('板块成分字段异常')
  seen.add(symbol);members.append(dict(code=symbol,name=name))
 return dict(code=code,source='新浪板块成分',collected_at=now_cn().isoformat(),members=members)


class SectorMembers:
 def __init__(self):self.lock=threading.Lock();self.cache={};self.running=set();self.errors={};self.attempt={}
 def _load(self,code):
  try:
   data=fetch(code)
   with self.lock:self.cache[code]=data;self.errors.pop(code,None)
  except Exception:
   with self.lock:self.errors[code]='板块成分获取失败'
  finally:
   with self.lock:self.running.discard(code)
 def view(self,code,enabled=True):
  if not isinstance(code,str) or not re.fullmatch(r'(?:new_|gn_)[A-Za-z0-9]+',code):return dict(data=None,running=False,error='该来源的板块成分尚未接入')
  with self.lock:
   if enabled and code not in self.running and time.monotonic()-self.attempt.get(code,float('-inf'))>=300:
    self.running.add(code);self.attempt[code]=time.monotonic();threading.Thread(target=self._load,args=(code,),daemon=True).start()
   return dict(data=self.cache.get(code),running=code in self.running,error=self.errors.get(code,''))
