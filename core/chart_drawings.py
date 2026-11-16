"""User annotations only. Never read by signals, alerts or order execution."""
import json
import math
import re
from datetime import date

LIMIT = 200


def scope(code, frame):
    if not isinstance(code, str) or not re.fullmatch(r'(?:sh|sz|bj)\d{6}', code):
        raise ValueError('画线股票代码无效')
    if frame not in ('daily', 'weekly'):
        raise ValueError('画线仅支持日K和周K')
    return code, frame


def validate(items):
    if not isinstance(items, list) or len(items) > LIMIT:
        raise ValueError(f'每个股票周期最多保存{LIMIT}个图形')
    clean, ids = [], set()
    for item in items:
        if not isinstance(item, dict):
            raise ValueError('画线数据无效')
        key, kind, points = item.get('id'), item.get('kind'), item.get('points')
        if not isinstance(key, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', key) or key in ids:
            raise ValueError('画线标识无效或重复')
        if kind not in ('line', 'rect') or not isinstance(points, list) or len(points) != 2:
            raise ValueError('仅支持两点线段或矩形')
        anchors = []
        for point in points:
            if not isinstance(point, dict):
                raise ValueError('画线坐标无效')
            day, price = point.get('date'), point.get('price')
            if not isinstance(day, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', day):
                raise ValueError('画线日期无效')
            date.fromisoformat(day)
            if type(price) not in (int, float) or not math.isfinite(price) or not 0 < price <= 1e9:
                raise ValueError('画线价格无效')
            anchors.append(dict(date=day, price=price))
        if anchors[0] == anchors[1] or (kind == 'rect' and (
                anchors[0]['date'] == anchors[1]['date'] or anchors[0]['price'] == anchors[1]['price'])):
            raise ValueError('图形范围太小，请重新绘制')
        result = dict(id=key, kind=kind, points=anchors)
        if 'color' in item:
            color = item['color']
            if not isinstance(color, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', color):
                raise ValueError('画线颜色无效')
            result['color'] = color.lower()
        if 'width' in item:
            width = item['width']
            if type(width) not in (int, float) or not math.isfinite(width) or not 1 <= width <= 6:
                raise ValueError('线宽应为1至6像素')
            result['width'] = width
        ids.add(key)
        clean.append(result)
    return clean


def load(store, code, frame):
    code, frame = scope(code, frame)
    rows = store.query('SELECT revision,payload FROM chart_drawings WHERE code=? AND frame=?', (code, frame))
    return dict(revision=rows[0]['revision'], items=validate(json.loads(rows[0]['payload']))) if rows else dict(revision=0, items=[])


def save(store, code, frame, revision, items):
    code, frame = scope(code, frame)
    if type(revision) is not int or revision < 0:
        raise ValueError('画线版本无效')
    items = validate(items)
    payload = json.dumps(items, ensure_ascii=False, separators=(',', ':'))
    # The conditional write itself is atomic across independent connections.
    # A Python lock alone only protects one Store instance.
    with store.lock, store.db:
        if revision == 0:
            cursor = store.db.execute(
                'INSERT INTO chart_drawings(code,frame,revision,payload) VALUES(?,?,1,?) '
                'ON CONFLICT(code,frame) DO NOTHING', (code, frame, payload))
        else:
            cursor = store.db.execute(
                'UPDATE chart_drawings SET revision=revision+1,payload=? '
                'WHERE code=? AND frame=? AND revision=?', (payload, code, frame, revision))
        if cursor.rowcount == 1:
            return dict(revision=revision + 1, items=items)
        current = load(store, code, frame)
        # A reply may be lost after commit. Retrying the same payload must not
        # advance its revision again or misreport a conflict.
        if current['revision'] == revision + 1 and current['items'] == items:
            return current
        return dict(conflict=True, **current)
