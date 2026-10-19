"""Provider metadata and factory; credentials never belong in display metadata."""
from decimal import Decimal
SOURCES=[dict(id='tencent',name='腾讯行情',available=True,website='https://gu.qq.com/',
    endpoints=dict(quote='https://qt.gtimg.cn/q=',minute='https://web.ifzq.gtimg.cn/appstock/app/day/query',daily='https://web.ifzq.gtimg.cn/appstock/app/fqkline/get'),
    description='公开行情接口；分钟通常覆盖最近数日。日线未复权；客户端统一成交量为股。'),
    dict(id='sina',name='新浪行情',available=False,website='https://finance.sina.com.cn/',endpoints=dict(minute='https://quotes.sina.cn/cn/api/jsonp_v2.php/=/CN_MarketDataService.getKLineData'),
    description='已接入历史补充，按整日缓存；开盘量及分钟边界不同，规则回放未认证。实时主来源仍为腾讯。')]

def provider_name(source):
    ident=source.get('provider') if isinstance(source,dict) else source
    return next((s['name'] for s in SOURCES if s['id']==ident),str(ident or '未知来源'))

def daily_view(code,row):
    """Normalize old raw Tencent cache without multiplying new normalized rows twice."""
    out=dict(row)
    if out.get('volume_unit')=='shares':return out
    if out.get('source')=='tencent':
        factor=1 if code.startswith('sh688') else 100
        out.update(raw_volume=str(out['volume']),raw_volume_unit='shares' if factor==1 else 'hands',
            volume=str(Decimal(str(out['volume']))*factor),volume_unit='shares',unit_basis='腾讯市场口径，普通A股手、科创股股；已用保存分钟累计量交叉核对')
    return out
