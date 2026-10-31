"""Exercise the real read-only RPCs with recorded inputs and an isolated store."""
import json
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from core.app import App
from core.index_technical import parse_daily

ROOT = Path(__file__).resolve().parents[1]
now = datetime.fromisoformat('2026-10-31T04:00:00+08:00')
payload = json.loads((ROOT / 'docs/author-trading-system-20261028/vwmacd-tencent-20261031.json').read_text())
rows = parse_daily(payload, '2026-01-01', '2026-10-30')
with tempfile.TemporaryDirectory() as directory:
    app = App(directory, start_worker=False)
    try:
        with patch('core.breadth.now_cn', return_value=now), \
             patch('core.csi300.now_cn', return_value=now), \
             patch('core.index_technical.now_cn', return_value=now), \
             patch('core.index_technical.fetch_daily', return_value=rows):
            app.index_technical.refresh(now)
            result = {'breadth': app.call('breadth', {}),
                      'index': app.call('index_technical', {}),
                      'csi300': app.call('csi300', {'day': '2026-10-30'})}
            if app.index_technical.error:
                raise ValueError(app.index_technical.error)
            print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    finally:
        app.store.db.close()
