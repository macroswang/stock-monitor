"""Read-only smoke test for the 市场机会 v2 report.

Copies the user's SQLite cache to a temporary directory (never writes the live
database), fetches the public limit-up/index/news sources, and prints or writes
the generated research for manual verification.

    .venv/bin/python scripts/opportunity_smoke.py
    .venv/bin/python scripts/opportunity_smoke.py --preview public/opportunity-preview.json
"""
import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import market_plan, market_pulse, market_radar, outlook_scheduler  # noqa: E402
from core.provider import now_cn  # noqa: E402
from core.store import Store  # noqa: E402

DEFAULT_DATA = Path.home() / 'Library/Application Support/com.xreddot.stockmonitor'


def load_inputs(data_dir, now):
    database = data_dir / 'monitor.sqlite3'
    if not database.exists():
        raise SystemExit(f'找不到本机数据库：{database}')
    temp = tempfile.mkdtemp(prefix='opportunity-smoke-')
    for suffix in ('', '-wal', '-shm'):
        source = Path(str(database) + suffix)
        if source.exists():
            shutil.copy2(source, Path(temp) / ('monitor.sqlite3' + suffix))
    store = Store(str(Path(temp) / 'monitor.sqlite3'))
    day = market_pulse.expected_quote_day(now)
    if not day:
        raise SystemExit('交易日历不足，无法确定行情日期')
    summaries = store.getcache('cn-ashare', 'breadth_day_v1', day)
    if not summaries:
        raise SystemExit(f'{day} 的全市场广度快照不存在，无法核验')
    summary = summaries[0]['data']
    raws = store.getcache('cn-ashare', 'breadth_raw_v1', day)
    if not raws:
        raise SystemExit(f'{day} 的逐股行情快照不存在')
    quotes = {row['code']: row for row in raws[0]['data']['quotes']}
    industry = _flow(store, 'eastmoney-industry', day)
    concept = _flow(store, 'sina-concept', day)
    feeds = []
    for region, lid in (('domestic', 2517), ('international', 2518)):
        try:
            feeds += outlook_scheduler.news(region, lid, now)
        except Exception as exc:
            print(f'新闻源未取得（{region}）：{type(exc).__name__}', file=sys.stderr)
    folder = data_dir / 'daily-outlook'
    issues = sorted(folder.glob('*.json'), reverse=True) if folder.exists() else []
    issues = [path for path in issues if now.date().isoformat() >= path.name[:10]][:20]
    if not issues:
        raise SystemExit('没有已生成的研判 issue，无法复用题材与方向候选')
    issue = json.loads(issues[0].read_text(encoding='utf-8'))
    return store, summary, quotes, industry, concept, feeds, issue


def _flow(store, code, day):
    rows = store.getcache(code, 'sector_flow_v1', day)
    if not rows:
        return None
    data = rows[-1]['data']
    return data if data.get('date') == day else None


def build(data_dir, now):
    store, summary, quotes, industry, concept, feeds, issue = load_inputs(data_dir, now)
    pulse = market_pulse.build(store, summary, quotes, industry, concept, feeds, now)
    report = market_plan.build(store, issue.get('ideas') or [], pulse, quotes, summary, now)
    speculation = market_radar.build(store, summary, quotes, concept, feeds, pulse.get('sentiment'),
                                     report.get('directions') or [], now)
    merged = dict(issue)
    merged.update(report)
    merged['pulse'] = pulse
    merged['radar'] = speculation['items']
    merged['radar_summary'] = speculation['summary']
    merged['screen_version'] = 9
    merged['quote_date'] = summary['date']
    merged['published_at'] = now.isoformat()
    merged['warnings'] = list(dict.fromkeys(pulse.get('warnings', []) + report.get('warnings', [])
                                           + speculation.get('warnings', [])))
    return merged, quotes


def summary_of(merged):
    pulse = merged.get('pulse') or {}
    market = pulse.get('market') or {}
    senti = pulse.get('sentiment') or {}
    capital = pulse.get('capital') or {}
    lines = ['定调：' + str(merged.get('verdict')) + ' / ' + str(merged.get('bias')) + ' / ' + str(merged.get('position')),
             '行情日期：' + str(merged.get('quote_date'))]
    breadth = market.get('breadth') or {}
    if breadth:
        lines.append(f"广度：上涨 {breadth['advance']} / 下跌 {breadth['decline']}，上涨占比 {breadth['advancing_percent']}%，"
                     f"成交额 {breadth['amount_yuan'] / 1e8:.0f} 亿，TRIN {breadth['trin']}")
    if senti:
        limits = senti.get('limit_up') or {}
        lines.append(f"人气：涨停 {limits.get('today')} / 跌停 {senti['limit_down']['today']}，封板率 {limits.get('sealed_rate')}，"
                     f"最高 {senti.get('max_board')} 板，温度 {senti.get('temperature')}")
        performance = senti.get('yesterday_performance')
        if performance:
            lines.append(f"昨日涨停今日：{performance['advance']}/{performance['checked']} 上涨，平均 {performance['avg_percent']}%，"
                         f"晋级 {performance['promote']}/{performance['count']}")
    if capital:
        lines.append('资金历史天数：' + str(capital.get('history_days')))
    for row in merged.get('directions') or []:
        lines.append(f"[{row['rank']}] {row['sector']}（{row['sector_kind']}）涨 {row['change']:+.2f}% "
                     f"净额 {row['net'] / 1e8:+.2f} 亿 近5日 {('—' if row['net_5d'] is None else format(row['net_5d'] / 1e8, '+.2f') + ' 亿')} "
                     f"→ {row['state']}：{row['why']}")
        for stock in row['stocks']:
            levels = stock.get('levels') or {}
            lines.append(f"    {stock['role']} {stock['name']} {stock['percent']:+.2f}% "
                         f"MA5={levels.get('ma5')} MA10={levels.get('ma10')} 买区 {stock['entry']['buy_low']}–{stock['entry']['buy_high']} "
                         f"止损 {stock['entry']['stop']}")
    for warning in merged.get('warnings') or []:
        lines.append('提示：' + warning)
    return '\n'.join(lines)


def preview_payload(merged, quotes, data_dir, now):
    """A compact, self-consistent sample for the browser-only preview."""
    day = merged['quote_date']
    sectors = {}
    for row in merged.get('directions') or []:
        sectors[row['sector_code']] = dict(change=row['change'], net=row['net'],
                                           time=merged['published_at'][:19], inferred=False)
    codes = {stock['code'] for row in merged.get('directions') or [] for stock in row['stocks']}
    for row in merged.get('directions') or []:
        codes.add(row['candidate']['code'])
        codes.update(item['code'] for item in row.get('peers') or [])
    day_quotes = [{key: value for key, value in quotes[code].items() if key in
                   ('code', 'price', 'previous_close', 'timestamp', 'day_low')} for code in sorted(codes) if code in quotes]
    pulse = merged.get('pulse') or {}
    for block in ('market', 'capital', 'sentiment'):
        if isinstance(pulse.get(block), dict) and 'by_code' in pulse[block]:
            pulse[block] = {key: value for key, value in pulse[block].items() if key != 'by_code'}
    if isinstance(pulse.get('sentiment'), dict):
        pulse['sentiment'] = {key: value for key, value in pulse['sentiment'].items() if key != 'by_code'}
    themes = [{key: value for key, value in theme.items() if key != 'members'}
              for theme in merged.get('themes') or []]
    ideas = [{key: value for key, value in idea.items() if key in ('sector', 'sector_code', 'sector_kind', 'change', 'net', 'stocks')}
             for idea in (merged.get('ideas') or [])[:3]]
    issue = dict(merged)
    issue['themes'] = themes[:60]
    issue['ideas'] = ideas
    return dict(issue=issue, quotes=day_quotes, sectors=sectors, day=day, batch=now.isoformat()[:19],
                schedule='本机预览样本', completed_slot=None,
                preview_note='浏览器只读预览样本：由本机已核对缓存生成，不是实时研判。')




REQUIRED = ('verdict', 'bias', 'position', 'horizon', 'pulse', 'directions', 'playbooks', 'timetable', 'risk')
STATE = {'可考虑建仓', '继续等', '观察', '回避'}
ROLE = {'低吸候选', '龙头', '中军', '弹性'}


def validate(merged):
    """Fail loudly when the generated report breaks the contract instead of showing partial data."""
    problems = []
    for key in REQUIRED:
        if key not in merged:
            problems.append('缺少字段 ' + key)
    if merged.get('bias') not in ('进攻', '试错', '防守'):
        problems.append('bias 非法：' + repr(merged.get('bias')))
    pulse = merged.get('pulse')
    if not isinstance(pulse, dict):
        problems.append('pulse 不是对象')
    else:
        for block in ('market', 'capital', 'sentiment', 'hotspots'):
            if block not in pulse:
                problems.append('pulse 缺少 ' + block)
    focus = merged.get('focus')
    if not isinstance(focus, dict) or not focus.get('sector'):
        problems.append('缺少首选方向 focus')
    picks = merged.get('top_picks')
    if not isinstance(picks, list) or not picks:
        problems.append('缺少建仓清单 top_picks')
    else:
        for pick in picks:
            label = str(pick.get('name'))
            for key in ('code', 'name', 'role', 'sector', 'state', 'price', 'buy_low', 'buy_high',
                        'chase', 'stop', 'target1', 'target2', 'sell_note', 'window', 'trigger', 'sizing'):
                if key not in pick:
                    problems.append(f'建仓清单 {label} 缺少 {key}')
            if not (pick.get('stop', 0) <= pick.get('buy_low', 0) <= pick.get('buy_high', 0) < pick.get('target1', 0)):
                problems.append(f'建仓清单 {label} 买卖点顺序异常')
    radar = merged.get('radar')
    if not isinstance(radar, list):
        problems.append('缺少炒作雷达 radar')
    else:
        stages = {'启动初期', '发酵', '加速/高潮', '分歧', '退潮', '观察'}
        for item in radar:
            label = str(item.get('theme'))
            for key in ('theme', 'kind', 'stage', 'stage_note', 'signals', 'limit_up_today', 'max_board',
                        'news_count', 'verdict', 'risk', 'watch', 'stocks', 'evidence'):
                if key not in item:
                    problems.append(f'炒作雷达 {label} 缺少 {key}')
            if item.get('stage') not in stages:
                problems.append(f'炒作雷达 {label} 阶段非法：{item.get("stage")}')
            for stock in item.get('stocks') or []:
                if stock.get('role') not in ('龙头', '跟风', '低吸候选'):
                    problems.append(f'炒作雷达 {label}/{stock.get("name")} 角色非法')
                entry = stock.get('entry') or {}
                if not (entry.get('stop', 0) < entry.get('buy_low', 0) <= entry.get('buy_high', 0) < entry.get('target1', 0)):
                    problems.append(f'炒作雷达 {label}/{stock.get("name")} 买卖点顺序异常')
    for direction in merged.get('directions') or []:
        label = str(direction.get('sector'))
        for key in ('rank', 'sector', 'sector_code', 'sector_kind', 'change', 'net', 'score', 'score_parts',
                    'state', 'why', 'opportunity', 'logic', 'risk', 'candidate', 'peers', 'stocks', 'timing', 'evidence'):
            if key not in direction:
                problems.append(f'{label} 缺少 {key}')
        if direction.get('state') not in STATE:
            problems.append(f'{label} state 非法：{direction.get("state")}')
        if not direction.get('stocks'):
            problems.append(f'{label} 没有重点股票')
        for stock in direction.get('stocks') or []:
            if stock.get('role') not in ROLE:
                problems.append(f"{label} 角色非法：{stock.get('role')}")
            entry = stock.get('entry') or {}
            if not all(isinstance(entry.get(key), (int, float)) for key in ('buy_low', 'buy_high', 'stop', 'chase')):
                problems.append(f"{label}/{stock.get('name')} 买入时机数值不完整")
            if not (entry.get('buy_low', 0) <= entry.get('buy_high', 0) <= entry.get('chase', 0)):
                problems.append(f"{label}/{stock.get('name')} 买区/追高价位顺序异常")
        gates = (direction.get('timing') or {}).get('gates') or []
        if len(gates) < 5:
            problems.append(f'{label} 条件不足：{len(gates)}')
    if len(merged.get('playbooks') or []) != 3:
        problems.append('剧本不是 3 条')
    if not any(item.get('active') for item in merged.get('playbooks') or []):
        problems.append('没有与当前定调对应的剧本')
    return problems


def main():
    parser = argparse.ArgumentParser(description='市场机会 v2 真实数据核验')
    parser.add_argument('--data-dir', type=Path, default=DEFAULT_DATA)
    parser.add_argument('--preview', type=Path, default=None)
    args = parser.parse_args()
    now = now_cn()
    merged, quotes = build(args.data_dir, now)
    print(summary_of(merged))
    problems = validate(merged)
    if problems:
        print('契约校验未通过：')
        for problem in problems:
            print('  - ' + problem)
        raise SystemExit(1)
    print('契约校验：通过（' + str(len(merged.get('directions') or [])) + ' 个方向）')
    if args.preview:
        args.preview.write_text(json.dumps(preview_payload(merged, quotes, args.data_dir, now), ensure_ascii=False, indent=1),
                                encoding='utf-8')
        print('已写入预览：' + str(args.preview))


if __name__ == '__main__':
    main()