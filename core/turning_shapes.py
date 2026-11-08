"""Candidate-time top/bottom signals, equivalent to the chart's shape-v1.

Q1 is an independent display/research filter. It never gates these observations.
"""
import math
from .turning_q1 import TIMES

# Preserve account rules and the execution contract; candidate event keys are distinct.
SIGNAL='shape-v1'
LABEL='图中候选点顶／底'


def signals(bars):
    by={};duplicates=set()
    for b in bars:
        if b['time'] in by:duplicates.add(b['time'])
        by[b['time']]=b
    all_bars=[by.get(t) for t in TIMES]
    def valid(b):
        if not b or b['time'] in duplicates or b.get('complete') is not True:return False
        try:
            return all(math.isfinite(float(b[k])) and float(b[k])>0 for k in ('close','average')) and math.isfinite(float(b['volume'])) and float(b['volume'])>=0
        except (KeyError,ValueError,TypeError):return False
    result=[];last={};eps=1e-9
    # The current complete minute emits without waiting for future reversal bars.
    # Keep the existing window, trading cutoff and spacing; Q1 is unchanged.
    for i in range(19,236):
        window=all_bars[i-19:i+1];bar=all_bars[i]
        if not all(valid(b) for b in window) or float(bar['volume'])<=0:continue
        p,vwap=float(bar['close']),float(bar['average'])
        prices=[float(b['close']) for b in window];support,resistance=min(prices),max(prices)
        deviation=p/vwap-1
        kind='bottom' if p<=support+eps and -deviation*100+eps>=.8 else 'top' if p>=resistance-eps and deviation*100+eps>=1.5 else None
        if kind is None:continue
        before=sum(float(b['volume']) for b in all_bars[i-5:i])/5
        m=dict(key=f"candidate-shape-v1|{kind}|{bar['time']}",kind=kind,time=bar['time'],price=p,
               candidateTime=bar['time'],candidatePrice=p,vwap=vwap,deviationPct=deviation*100,
               support=support,resistance=resistance,movePct=0,volumeRatio=float(bar['volume'])/before if before>0 else None)
        previous=last.get(kind)
        if previous and TIMES.index(m['time'])-TIMES.index(previous['time'])<30:continue
        if previous and result[-1]['kind']==kind:
            advance=m['candidatePrice']-previous['candidatePrice'] if kind=='top' else previous['candidatePrice']-m['candidatePrice']
            if advance+eps<max(.02,previous['candidatePrice']*.008):continue
        result.append(m);last[kind]=m
    return result


def liquidity(bars,stamp):
    """Execution-size evidence, independent of shape detection and Q1 screening."""
    by={b['time']:b for b in bars};index=TIMES.index(stamp)
    try:
        rows=[by[t] for t in TIMES[index-4:index+1]]
        if len(rows)!=5 or any(b.get('complete') is not True for b in rows):raise ValueError()
        volumes=[float(b['volume']) for b in rows]
        import math
        if not all(math.isfinite(v) and v>=0 for v in volumes):raise ValueError()
        return dict(meanShares=sum(volumes)/5,currentShares=volumes[-1])
    except (ValueError,TypeError,KeyError):return {}
