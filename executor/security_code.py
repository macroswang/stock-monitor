"""Resolve a holding through a verified native stock-code field, without ordering."""
import re
from .adb import AdbError,find_by_id,wait_until
from .trade import TradePage


def code_and_name(text,expected_name):
    match=re.fullmatch(r'(\d{6})\s+(.+)',text.strip())
    if not match or match.group(2).replace(' ','')!=expected_name.replace(' ',''):
        raise ValueError('证券代码输入框的名称与所选持仓不符，已停止')
    return match.group(1)


def zhangle_code(adb,row,nodes,verify):
    verify(nodes)
    names=[n for n in nodes if n.resource_id.endswith('/stock_name') and n.text.strip()==row['name']]
    if len(names)!=1:
        raise ValueError('无法唯一定位持仓行，拒绝按名称猜测股票代码')
    adb.tap_node(names[0])
    current=adb.nodes()
    entry=find_by_id(current,'pop_buy')
    if entry is None or entry.text!='买入':
        raise ValueError('持仓行菜单结构未识别，未读取代码')
    adb.tap_node(entry)
    page=TradePage(adb)
    try:
        def loaded():
            try:
                current=adb.nodes(retries=1)
                field=find_by_id(current,'trade_editText')
                return current if field and re.match(r'^\d{6}\s',field.text) else None
            except AdbError:
                return None
        current=wait_until(loaded,timeout=30,interval=.4)
        if not current:
            raise ValueError('证券代码表单加载失败；未提交委托')
        code=code_and_name(find_by_id(current,'trade_editText').text,row['name'])
        return dict(row,code=code,code_source='broker_native_form')
    finally:
        page.close()
        verify(adb.nodes())


def ths_code(adb,row,nodes,verify):
    from .ths_order import ThsOrderPage,read_form
    verify(nodes)
    names=[n for n in nodes if n.text.strip()==row['name']]
    if len(names)!=1:raise ValueError('无法唯一定位同花顺持仓，未读取代码')
    entries=[n for n in nodes if n.resource_id.endswith('/function_text') and n.text=='买入']
    if not entries:
        adb.tap_node(names[0]);nodes=adb.nodes()
        entries=[n for n in nodes if n.resource_id.endswith('/function_text') and n.text=='买入']
    if len(entries)!=1:raise ValueError('同花顺持仓菜单无法唯一识别')
    adb.tap_node(entries[0]);page=ThsOrderPage(adb)
    try:
        current=page.wait(lambda ns:read_form(ns) is not None and bool(read_form(ns).code) and find_by_id(ns,'stockname') is not None)
        form=read_form(current);name=find_by_id(current,'stockname').text.strip()
        if name.replace(' ','')!=row['name'].replace(' ',''):raise ValueError('同花顺证券代码与持仓名称不符')
        verify(current)
        return dict(row,code=form.code,code_source='broker_native_form')
    finally:
        current=adb.nodes()
        tabs=[n for n in current if n.resource_id.endswith('/btn') and n.text=='持仓']
        if len(tabs)!=1:raise ValueError('无法返回同花顺持仓，已停止同步')
        adb.tap_node(tabs[0])
        restored=page.wait(lambda ns:find_by_id(ns,'position_table_view') is not None)
        verify(restored)
