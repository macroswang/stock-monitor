"""生成股票池终端表格浏览器只读预览数据（pool / pool_backtest）。

用法（只读副本）：
  sqlite3 "$HOME/Library/Application Support/com.xreddot.stockmonitor/monitor.sqlite3" ".backup '/tmp/poolpreview/monitor.sqlite3'"
  Code/stock-monitor/.venv/bin/python scripts/build_pool_previews.py /tmp/poolpreview/monitor.sqlite3 \
    --archive "$HOME/Library/Application Support/com.xreddot.stockmonitor/daily-outlook"
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.store import Store  # noqa: E402
from core.pool import Pool  # noqa: E402
from core.provider import get  # noqa: E402
from core.breadth import parse_quotes  # noqa: E402

QUOTE_URL = 'https://qt.gtimg.cn/q='


def fetch_quotes(codes):
    """为预览补一次实时行情（量比/换手/振幅/流通市值），失败返回空 dict。"""
    quotes = {}
    for start in range(0, len(codes), 50):
        chunk = codes[start:start + 50]
        try:
            text = get(QUOTE_URL + ','.join(chunk), 'gb18030')
            quotes.update(parse_quotes(text, set(chunk)))
        except Exception as exc:
            print('quote batch failed', type(exc).__name__, exc)
    return quotes


class App:
    """预览生成只需要 store/dir，不启动线程、不联网。"""


def load_issues(folder: Path):
    issues = []
    for path in sorted(folder.glob('*_*.json')):
        try:
            issue = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError, TypeError):
            continue
        if not isinstance(issue, dict) or not issue.get('published_at'):
            continue
        if issue.get('screen_version', 0) < 9:
            continue
        issues.append(issue)
    issues.sort(key=lambda item: item['published_at'])
    return issues


def dump(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding='utf-8')
    print('written', path, len(path.read_bytes()), 'bytes')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('db', help='monitor.sqlite3 的只读副本路径')
    parser.add_argument('--archive', required=True, help='daily-outlook 目录')
    parser.add_argument('--out', default=str(ROOT / 'public'))
    parser.add_argument('--no-quotes', action='store_true', help='不拉实时行情（预览里量比/换手将为空）')
    args = parser.parse_args()

    db = Path(args.db)
    folder = Path(args.archive).expanduser()
    if not db.is_file():
        raise SystemExit('数据库副本不存在：' + str(db))
    if not folder.is_dir():
        raise SystemExit('研判存档目录不存在：' + str(folder))

    app = App()
    app.store = Store(db)
    app.dir = folder.parent
    pool = Pool(app)

    issues = load_issues(folder)
    print('issues', len(issues), issues[0]['published_at'] if issues else '-', '→', issues[-1]['published_at'] if issues else '-')
    record = getattr(pool, 'record_episodes', None)
    if record is None:
        print('WARN: Pool.record_episodes 不存在，跳过回填')
    else:
        for issue in issues:
            try:
                record(issue)
            except Exception as exc:
                print('episode failed', issue.get('published_at'), type(exc).__name__, exc)

    codes = [row['code'] for row in app.store.query('SELECT code FROM pool')]
    if not args.no_quotes and codes:
        quotes = fetch_quotes(codes)
        pool.quotes = quotes
        print('live quotes', len(quotes), '/', len(codes))
    else:
        pool.quotes = {}

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    view = pool.view(limit=200)
    dump(out / 'pool-preview.json', view)

    backtest = getattr(pool, 'pool_backtest', None) or getattr(pool, 'backtest', None)
    if backtest is None:
        print('WARN: Pool.pool_backtest 不存在，生成空回测预览')
        dump(out / 'pool-backtest-preview.json', {'rows': [], 'coverage': {'rows': 0, 'with_returns': 0, 'bench': '上证指数', 'daily_codes': 0, 'note': '回测暂不可用'}})
    else:
        dump(out / 'pool-backtest-preview.json', backtest())

    entries = view.get('entries') or []
    print('pool entries', len(entries),
          'with episodes', sum(1 for e in entries if (e.get('episodes') or {}).get('total')),
          'with quant', sum(1 for e in entries if (e.get('quant') or {}).get('volume_ratio') is not None),
          'with tags', sum(1 for e in entries if any((e.get('tags') or {}).values())))


if __name__ == '__main__':
    main()
