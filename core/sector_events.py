"""按来源时间计算可复核的板块采样变化；不参与正式交易规则。"""
from datetime import datetime,time,timedelta
import math
from .provider import CN


def session(stamp):
    t=stamp.astimezone(CN).time()
    if time(9,30)<=t<=time(11,30):return 'am'
    if time(13,0)<=t<=time(15,0):return 'pm'
    return None


def build_observations(snapshots,now,day):
    now=now.astimezone(CN);series={}
    for snapshot in snapshots:
        if snapshot.get('date')!=day or snapshot.get('source')!='东方财富行业板块资金流':continue
        for row in snapshot.get('observations',[]):
            try:
                stamp=datetime.fromisoformat(row['source_time']);change=float(row['change_percent']);net=float(row['net_yuan'])
                if stamp.tzinfo is None or stamp.astimezone(CN).date().isoformat()!=day or stamp>now+timedelta(seconds=5) or not session(stamp) or not math.isfinite(change) or not math.isfinite(net):continue
                points=series.setdefault(row['code'],{'name':row['name'],'points':[]})['points']
                if not any(p['time']==stamp.isoformat() for p in points):points.append(dict(time=stamp.isoformat(),change=change,net=net))
            except (KeyError,TypeError,ValueError,OverflowError):continue
    events=[]
    for code,group in series.items():
        pts=sorted(group['points'],key=lambda x:x['time']);group['points']=pts
        if not pts:continue
        latest=pts[-1];end=datetime.fromisoformat(latest['time'])
        if end.date()!=now.date() or session(end)!=session(now) or session(now) is None or not 0<=(now-end).total_seconds()<=180:continue
        candidates=[p for p in pts[:-1] if session(datetime.fromisoformat(p['time']))==session(end) and 300<=(end-datetime.fromisoformat(p['time'])).total_seconds()<=480]
        if not candidates:continue
        base=candidates[-1];change=latest['change']-base['change'];net=latest['net']-base['net']
        # 暂定研究阈值，表示涨跌幅变化超过 0.3 个百分点且资金方向一致。
        if change>=0.3 and net>0:
            label='启动观察'
            # 最近两个同源采样均满足上行条件，才将状态升级为持续走强。
            if len(pts)>=3:
                prior=pts[-2];prior_time=datetime.fromisoformat(prior['time'])
                older=[p for p in pts[:-2] if session(datetime.fromisoformat(p['time']))==session(prior_time) and 300<=(prior_time-datetime.fromisoformat(p['time'])).total_seconds()<=480]
                if older and session(prior_time)==session(end) and 0<(end-prior_time).total_seconds()<=180 and prior['change']-older[-1]['change']>=0.3 and prior['net']-older[-1]['net']>0:
                    label='持续走强'
        elif change<=-0.3 and net<0:label='转弱提醒'
        else:continue
        events.append(dict(code=code,name=group['name'],time=latest['time'],start=base['time'],label=label,change=change,net=net))
    events.sort(key=lambda e:(e['time'],e['code']),reverse=True)
    return dict(events=events,series=series,date=day,status='盘中采样观察 · 实验阈值，未验证为买卖信号')
