"""Read-only prospective report. Immutable rule cohorts; pending is never zero."""
import argparse,json,sqlite3,statistics,sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE))
from research.ma250_execution import forward_outcomes
from core.ma250_pullback import prepare
DEFAULT_DB=Path.home()/'Library'/'Application Support'/'com.xreddot.stockmonitor'/'monitor.sqlite3'
OUT=BASE/'docs'/'ma250-pullback'/'prospective'


def load(db):
    c=sqlite3.connect(f'file:{db}?mode=ro',uri=True);c.row_factory=sqlite3.Row
    journal=[];tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'ma250_journal' in tables:
        saved={}
        for row in c.execute('SELECT code,day,rule_id,phase,payload FROM ma250_journal ORDER BY phase DESC'):
            key=(row['code'],row['day'],row['rule_id'])
            if key not in saved or row['phase']=='confirmed':saved[key]=dict(code=row['code'],day=row['day'],rule_id=row['rule_id'],data=json.loads(row['payload']))
        journal.extend(saved.values())
    # Historical v2 remains its own explicitly unversioned cohort.
    journal += [dict(code=r['code'],day=r['day'],rule_id='legacy-v2-unfrozen',data=json.loads(r['payload']))
                for r in c.execute("SELECT code,day,payload FROM cache WHERE kind='ma250_journal_v1'")]
    bars=defaultdict(list)
    for r in c.execute("SELECT code,day,payload FROM cache WHERE kind='daily' ORDER BY code,day"):
        d=json.loads(r['payload'])
        bars[r['code']].append(dict(d,date=r['day']))
    for code in bars:
        try:bars[code]=prepare(bars[code])['rows']
        except (KeyError,ValueError,TypeError,OverflowError,AttributeError):bars[code]=[]
    index=c.execute("SELECT payload FROM cache WHERE code='sh000300' AND kind='index_regime_v1' ORDER BY day DESC LIMIT 1").fetchone()
    sessions=sorted(r['date'] for r in json.loads(index['payload']).get('rows',[])) if index else None
    c.close();return journal,bars,sessions


def evaluate(journal,bars,sessions=None):
    out=[]
    for row in journal:
        data=row['data'];signal=data.get('signal')
        if not signal:continue
        series=bars.get(row['code']) or [];i=next((i for i,b in enumerate(series) if b['date']==row['day']),None)
        pending=data.get('status')=='awaiting_data' or i is None
        result=forward_outcomes(row['code'],series,i,sessions) if not pending else None
        forward=result['forward'] if result else {str(h):None for h in (5,10,20,60)}
        status='awaiting_confirmation' if pending else result['entry']['status']
        if status=='entered':status='complete' if forward['20'] is not None else 'observing'
        out.append(dict(code=row['code'],date=row['day'],strong=bool(signal.get('strong')),
            rule_id=row.get('rule_id') or (data.get('rule') or {}).get('rule_id') or 'legacy-unfrozen',
            market=data.get('market_above'),reasons=signal.get('strong_reasons') or [],forward=forward,
            status=status,entry_date=result['entry']['date'] if result else None))
    return out


def summary(rows):
    net=[r['forward']['20'] for r in rows if r['forward']['20'] is not None]
    return dict(samples=len(net),mean=statistics.mean(net) if net else None,
                win=sum(v>0 for v in net)/len(net) if net else None,
                pending=sum(r['forward']['20'] is None and r.get('status')!='entry_unavailable' for r in rows),
                unavailable=sum(r.get('status')=='entry_unavailable' for r in rows))


def mark(rows,observations=None):
    lines=['# 年线信号：前瞻日志','',f'生成：{datetime.now().astimezone().isoformat()}',
           f'已记录信号 {len(rows)} 条；已完成20日观察 {sum(r["forward"]["20"] is not None for r in rows)} 条。',
           '规则版本分别统计；等待次日开盘、等待确认、未到期均保留。无法入场单列，不当作零收益。','']
    if observations is not None:lines.append(f'已记录股票日观察 {len(observations)} 条，含无信号与数据待补；未运行日期没有观察记录，不补造前瞻样本。')
    for rule in sorted({r['rule_id'] for r in rows}):
        lines += ['',f'## {rule}','','|档位|完整样本|20日均值|胜率|待观察|无法入场|','|---|---|---|---|---|---|']
        for label,strong in [('强信号',True),('普通观察',False)]:
            m=summary([r for r in rows if r['rule_id']==rule and r['strong']==strong]);avg='—' if m['mean'] is None else f"{m['mean']:+.2f}%";win='—' if m['win'] is None else f"{m['win']*100:.1f}%"
            lines.append(f"|{label}|{m['samples']}|{avg}|{win}|{m['pending']}|{m['unavailable']}|")
    return '\n'.join(lines)+'\n'


def main():
    p=argparse.ArgumentParser();p.add_argument('--db',default=str(DEFAULT_DB));p.add_argument('--out',default=str(OUT));a=p.parse_args()
    journal,bars,sessions=load(a.db);rows=evaluate(journal,bars,sessions);out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    (out/'report.md').write_text(mark(rows,journal));(out/'report.json').write_text(json.dumps(rows,ensure_ascii=False,indent=1));print('signals',len(rows))

if __name__=='__main__':main()
