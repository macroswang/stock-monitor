"""Bounded traversal of native holdings lists; never submits orders.

Missing security codes remain unresolved; the UI requires account-scoped code
confirmation against a public quote instead of guessing from a display name.
"""
from .adb import find_by_id


def collect(adb, nodes, list_id, parse, funds, max_pages=30, verify=None, resolve=None):
    def read(current):
        if verify is not None:
            verify(current)
        container = find_by_id(current, list_id)
        if not container:
            raise ValueError('持仓列表已离开或加载失败，请重新同步')
        rows = parse(current, container.bounds)
        # Prices/P&L move while reading. Position identity and quantities must stay stable.
        signature = tuple((r.get('name'), r.get('code'), r.get('quantity'), r.get('sellable')) for r in rows)
        return container, rows, signature

    def swipe(container, down):
        x1,y1,x2,y2 = container.bounds
        if x2-x1 < 20 or y2-y1 < 80:
            raise ValueError('持仓列表可读区域不足，请展开券商持仓页面')
        x = (x1+x2)//2
        top,bottom = y1+25,y2-25
        adb.shell('input','swipe',str(x),str(top if down else bottom),str(x),str(bottom if down else top),'450')
        return adb.nodes()

    container, rows, previous = read(nodes)
    if not rows:
        empty = any(any(t in n.text for t in ('暂无持仓','无持仓','没有持仓','您还没有持仓')) for n in nodes)
        return dict(funds=funds, positions=[], complete=empty, warning='' if empty else '持仓列表为空但没有明确空仓提示，请重新同步')
    # Return to the top first. The list may have been left in its middle by the user.
    for _ in range(max_pages):
        nodes = swipe(container, True)
        container, rows, current = read(nodes)
        if current == previous:
            break
        previous = current
    else:
        return dict(funds=funds, positions=rows, complete=False, warning='未能确认持仓列表顶部，已保留上次数据')
    found, order = {}, []
    for _ in range(max_pages):
        for row in rows:
            key = row.get('name','')
            if not key:
                raise ValueError('持仓名称缺失，已停止同步')
            if key in found:
                old = found[key]
                if any(old.get(k) != row.get(k) for k in ('quantity','sellable')) or (old.get('code') and row.get('code') and old['code']!=row['code']):
                    raise ValueError('读取过程中持仓数量发生变化或同名持仓无法区分，请重新同步')
                row=dict(row,code=row.get('code') or old.get('code',''))
            else:
                order.append(key)
                if resolve and not row.get('code'):
                    row=resolve(row,nodes)
                    nodes=adb.nodes()
                    container,restored,_=read(nodes)
                    if [(p.get('name'),p.get('quantity'),p.get('sellable')) for p in restored] != [(p.get('name'),p.get('quantity'),p.get('sellable')) for p in rows]:
                        raise ValueError('读取代码后持仓页面已变化，请重新同步')
            found[key] = row
        previous = tuple((r.get('name'),r.get('quantity'),r.get('sellable')) for r in rows)
        nodes = swipe(container, False)
        container, rows, _signature = read(nodes)
        current = tuple((r.get('name'),r.get('quantity'),r.get('sellable')) for r in rows)
        if current == previous:
            # A second independent read avoids accepting an intermediate loading frame.
            confirm = read(adb.nodes())[1]
            if tuple((r.get('name'),r.get('quantity'),r.get('sellable')) for r in confirm) == current:
                return dict(funds=funds,positions=[found[k] for k in order],complete=True)
    return dict(funds=funds,positions=[found[k] for k in order],complete=False,warning='持仓超过本次读取上限，保留旧数据，不判定清仓')
