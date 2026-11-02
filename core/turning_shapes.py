"""The chart's labelled confirmed top/bottom shapes, equivalent to shape-v1.

Q1 is an independent display/research filter. It never gates these observations.
"""
from .turning_q1 import TIMES,raw_signals

SIGNAL='shape-v1'
LABEL='图中已确认的顶／底'


def signals(bars):
    result=[];last={};eps=1e-9
    for m in raw_signals(bars):
        kind=m['kind'];previous=last.get(kind)
        if (-m['deviationPct'] if kind=='bottom' else m['deviationPct'])+eps < (.8 if kind=='bottom' else 1.5):continue
        if previous and TIMES.index(m['time'])-TIMES.index(previous['time'])<30:continue
        if previous and result[-1]['kind']==kind:
            advance=m['candidatePrice']-previous['candidatePrice'] if kind=='top' else previous['candidatePrice']-m['candidatePrice']
            if advance+eps<max(.02,previous['candidatePrice']*.008):continue
        accepted=dict(m,key=f"confirmed-shape-v1|{kind}|{m['candidateTime']}|{m['time']}")
        result.append(accepted);last[kind]=accepted
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
