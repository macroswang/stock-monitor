"""Tencent public data adapter. Never merge providers silently."""
import json, re
from datetime import datetime
from decimal import Decimal
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

CN=ZoneInfo('Asia/Shanghai')

def now_cn(): return datetime.now(CN)

def symbol(value):
    value=value.strip().lower()
    if re.fullmatch(r'\d{6}',value): value=('sh' if value[0] in '69' else 'sz')+value
    if not re.fullmatch(r'(sh6\d{5}|sz[03]\d{5})',value): raise ValueError('请输入沪深A股六位代码，如 603002 或 sz000815')
    return value

def get(url, encoding='utf-8'):
    req=Request(url,headers={'User-Agent':'Mozilla/5.0','Referer':'https://gu.qq.com/'})
    with urlopen(req,timeout=10) as r: return r.read().decode(encoding)

class Tencent:
    def quote(self, code):
        code=symbol(code)
        text=get('https://qt.gtimg.cn/q='+code,'gb18030')
        if '="' not in text: raise ValueError('股票不存在或暂时没有行情')
        fields=text.split('="',1)[1].rsplit('"',1)[0].split('~')
        if len(fields)<49: raise ValueError('行情返回字段不足')
        if fields[2]!=code[2:]: raise ValueError('返回股票代码不一致，拒绝使用行情')
        stamp=datetime.strptime(fields[30],'%Y%m%d%H%M%S').replace(tzinfo=CN)
        p=Decimal(fields[3]); limit=Decimal(fields[47])
        if not p.is_finite() or not limit.is_finite() or not p>0 or not limit>=p: raise ValueError('缺少可验证的实时价格或涨停价')
        return dict(code=code,name=fields[1],price=str(p),previous_close=fields[4],
            open=fields[5],volume=str(Decimal(fields[6])*(1 if code.startswith('sh688') else 100)),volume_unit='shares',
            high=fields[33],low=fields[34],limit_up=str(limit),limit_down=fields[48],timestamp=stamp.isoformat(),
            date=stamp.date().isoformat(),change=fields[32],source='tencent')

    def minutes(self,code,now=None):
        now=now or now_cn()
        raw=json.loads(get('https://web.ifzq.gtimg.cn/appstock/app/day/query?'+urlencode({'code':symbol(code)})))
        data=raw['data'][code]
        result=[]
        for day in data['data']:
            ds=day['date']; date=f'{ds[:4]}-{ds[4:6]}-{ds[6:]}'
            rows=[line.split() for line in day['data']]
            if not rows: continue
            labels=[r[0] for r in rows]
            if any(len(r)<4 for r in rows) or labels!=sorted(set(labels)):
                raise ValueError('分钟标签重复或顺序异常')
            if '0930' not in labels:
                raise ValueError('缺少09:30累计量，无法可靠剔除集合竞价')
            # Amount/volume must distinguish hands vs shares, using observed prices as bounds.
            last=rows[-1]; cumulative=Decimal(last[2]); amount=Decimal(last[3])
            prices=[Decimal(r[1]) for r in rows if Decimal(r[1])>0]
            if cumulative<=0 or not prices: continue
            avg=amount/cumulative
            factors=[m for m in (1,100) if min(prices)*Decimal('.75')<=avg/m<=max(prices)*Decimal('1.25')]
            if len(factors)!=1: raise ValueError('无法确认腾讯分钟成交量单位')
            prev=0; bars=[]
            for t,price,total,turnover,*_ in rows:
                total=int(total); vol=(total-prev)*factors[0]; prev=total
                if vol<0: raise ValueError('累计成交量倒退')
                label=t[:2]+':'+t[2:]
                # Exclude current endpoint and use a 3-second finalization grace period.
                end=datetime.fromisoformat(date+'T'+label+':00').replace(tzinfo=CN)
                complete=(now-end).total_seconds()>=3
                average=None
                try:
                    cash=Decimal(turnover);shares=Decimal(total)*factors[0]
                    if cash.is_finite() and cash>=0 and shares>0:average=str(cash/shares)
                except Exception:pass
                bars.append(dict(time=label,close=price,volume=vol,complete=complete,average=average))
            result.append(dict(date=date,bars=bars,previous_close=day.get('prec'),source='tencent',volume_unit='shares',
                multiplier=factors[0],label_semantics='end_pending_live_verification'))
        return result

    def daily(self,code,start,end):
        raw=json.loads(get('https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?'+urlencode(
            {'param':f'{symbol(code)},day,{start},{end},2000,'})))
        data=raw['data'][code]
        rows=data.get('day',[])
        if 'day' not in data: raise ValueError('日线来源没有返回未复权数据字段')
        return [dict(date=r[0],open=r[1],close=r[2],high=r[3],low=r[4],volume=str(Decimal(r[5])*(1 if code.startswith('sh688') else 100)),raw_volume=r[5],raw_volume_unit='shares' if code.startswith('sh688') else 'hands',volume_unit='shares',
                     source='tencent',adjustment='none') for r in rows if start<=r[0]<=end]
