"""同花顺原生买卖表单。预填不点击任何委托按钮。"""
import re
import time
from dataclasses import dataclass,asdict
from decimal import Decimal,InvalidOperation
from .adb import Adb,AdbError,find_by_id,wait_until
from .ths import ThsTrade,ThsError
from .ths import read_status,PACKAGE
from .identity import account_matches
from .trade import TradeForm


def inputs(nodes):
    return sorted([n for n in nodes if 'EditText' in n.class_name and not n.resource_id.endswith('/auto_stockcode')],key=lambda n:n.bounds[1])


def read_form(nodes):
    if find_by_id(nodes,'dialog_title') is not None:return None
    codes=[n for n in nodes if n.resource_id.endswith('/auto_stockcode') and 'EditText' in n.class_name]
    fields=inputs(nodes)
    tabs=[n for n in nodes if n.resource_id.endswith('/btn') and n.selected and n.text in ('买入','卖出')]
    if find_by_id(nodes,'stock_search') or len(codes)!=1 or len(fields)!=2 or len(tabs)!=1:
        return None
    code=codes[0].text.strip()
    if not re.fullmatch(r'\d{6}',code):code=''
    clean=lambda n:n.text.strip() if re.fullmatch(r'\d+(?:\.\d+)?',n.text.strip()) else ''
    return TradeForm('buy' if tabs[0].text=='买入' else 'sell',code,clean(fields[0]),clean(fields[1]),'', '',tabs[0].text)


def requires_confirmation(nodes):
    labels=[n for n in nodes if n.text=='委托撤单免二次确认']
    if len(labels)!=1:raise ThsError('无法核验券商二次确认设置，禁止触碰委托按钮')
    label=labels[0]
    statuses=[n for n in nodes if n.resource_id.endswith('/tv_func_status') and n.center[0]>label.center[0] and label.bounds[1]<=n.center[1]<=label.bounds[3]]
    if len(statuses)!=1 or statuses[0].text not in ('未开启','已开启'):
        raise ThsError('二次确认设置状态无法唯一识别，禁止触碰委托按钮')
    return statuses[0].text=='未开启'


@dataclass(frozen=True)
class Confirmation:
    side:str
    code:str
    name:str
    quantity:int
    price:str


def parse_confirmation(nodes):
    def one(rid):
        matches=[n for n in nodes if n.resource_id.endswith('/'+rid)]
        return matches[0] if len(matches)==1 else None
    fields={k:one(k) for k in ('dialog_title','stock_name_value','stock_code_value','number_value','price_value','cancel_btn','ok_btn')}
    if not all(fields.values()):return None
    label={'委托买入确认':'buy','委托卖出确认':'sell'}.get(fields['dialog_title'].text)
    if not label or fields['cancel_btn'].text!='取消' or fields['ok_btn'].text!=('确认买入' if label=='buy' else '确认卖出'):return None
    code,quantity,price=(fields[k].text.strip() for k in ('stock_code_value','number_value','price_value'))
    if not re.fullmatch(r'\d{6}',code) or not re.fullmatch(r'[1-9]\d*',quantity):return None
    try:
        value=Decimal(price)
        if not value.is_finite() or value<=0:return None
    except InvalidOperation:return None
    return Confirmation(label,code,fields['stock_name_value'].text.strip(),int(quantity),price)


def parse_result(nodes):
    title=find_by_id(nodes,'dialog_title')
    if not title or parse_confirmation(nodes):return None
    messages=[n.text for n in nodes if n.resource_id.rsplit('/',1)[-1] in ('dialog_message','message') and n.text]
    if not messages:
        # Some Galaxy dialogs expose an unlabelled text body. Read only inside
        # a bounded modal containing its title and acknowledgement button.
        buttons=[n for n in nodes if n.text in ('确定','知道了','关闭','确认') and n.bounds[1]>=title.bounds[3]]
        inside=lambda outer,inner:outer[0]<=inner[0] and outer[1]<=inner[1] and outer[2]>=inner[2] and outer[3]>=inner[3]
        area=lambda b:(b[2]-b[0])*(b[3]-b[1])
        screen=max((area(n.bounds) for n in nodes),default=0)
        containers=[n for n in nodes if any(k in n.class_name for k in ('Layout','ViewGroup','Dialog')) and inside(n.bounds,title.bounds)
                    and area(n.bounds)<screen*.8 and any(inside(n.bounds,b.bounds) for b in buttons)]
        if containers:
            box=min(containers,key=lambda n:area(n.bounds)).bounds
            messages=[n.text for n in nodes if n.text and n is not title and inside(box,n.bounds)
                      and not n.password and 'EditText' not in n.class_name and n.text not in ('确定','知道了','关闭','确认')]
    if not messages and title.text.strip() in ('系统信息','系统提示','提示','信息'):return None
    text=title.text+' '+' '.join(dict.fromkeys(messages))
    success=any(t in text for t in ('委托成功','委托提交成功','委托已提交','委托已受理','申报成功'))
    error=any(t in text for t in ('失败','拒绝','不足','错误','无效','不允许'))
    if (success and error) or any(t in text for t in ('网络','超时','断开','连接异常','查询失败','读取失败','结果未知')):status='unknown'
    elif error:status='rejected'
    elif success:status='accepted'
    else:status='unknown'
    result=dict(status=status,submitted=status=='accepted',message=text.strip())
    orders=set(re.findall(r'(?:委托编号|委托号|合同编号|合同号)\s*[:：]?\s*([A-Za-z0-9_-]+)',text))
    if len(orders)>1:result.update(status='unknown',submitted=False)
    if status=='accepted' and len(orders)==1:result['order_id']=orders.pop()
    return result


class ThsOrderPage:
    def __init__(self,adb=None,expected_account=None):
        self.adb=adb or Adb();self.expected_account=expected_account
        self._verified_form_account=None;self._verified_form_at=0;self._pending_plan=None
        self._last_form_nodes=None

    def verify_account(self,nodes):
        if self.expected_account is None:return
        status=read_status(nodes,self.adb.current_focus())
        if account_matches(status.account_masked,self.expected_account) and '银河' in status.broker_name and status.app_foreground:
            self._verified_form_account=self.expected_account;self._verified_form_at=time.monotonic()
            return
        # Native confirmation dialogs hide the underlying capital-account header.
        # Accept only the exact plan just bound to that header, in the same app;
        # a visible mismatched/partial header can never use this exception.
        confirmation=parse_confirmation(nodes)
        if (not status.account_masked and not status.broker_name and status.app_foreground and confirmation is not None
            and confirmation==self._pending_plan and self._verified_form_account==self.expected_account
            and 0<=time.monotonic()-self._verified_form_at<=30):
            return
        raise ThsError('确认前券商或资金账户不符，已阻止委托')

    def snapshot(self):return self.adb.nodes(retries=1)

    def wait(self,predicate,timeout=25):
        def check():
            try:
                nodes=self.snapshot()
                return nodes if predicate(nodes) else None
            except AdbError:return None
        result=wait_until(check,timeout=timeout,interval=.4)
        if not result:raise ThsError('同花顺表单未就绪，未发送委托')
        return result

    def open(self,side):
        if side not in ('buy','sell'):raise ValueError('买卖方向无效')
        nodes=self.snapshot()
        form=read_form(nodes)
        if not form:
            nodes=ThsTrade(self.adb).open_trade_tab()
            entry=find_by_id(nodes,'menu_buy')
            if not entry:raise ThsError('找不到同花顺买入表单入口')
            self.adb.tap_node(entry)
            nodes=self.wait(lambda ns:read_form(ns) is not None)
        label='买入' if side=='buy' else '卖出'
        form=read_form(nodes)
        if form.side!=side:
            tabs=[n for n in nodes if n.resource_id.endswith('/btn') and n.text==label]
            if len(tabs)!=1:raise ThsError('买卖标签无法唯一识别')
            self.adb.tap_node(tabs[0])
            nodes=self.wait(lambda ns:read_form(ns) is not None and read_form(ns).side==side)
        return nodes

    def set_code(self,nodes,code):
        if not re.fullmatch(r'\d{6}',code):raise ValueError('股票代码必须为6位数字')
        form=read_form(nodes)
        name=find_by_id(nodes,'stockname')
        if form and form.code==code and name and name.text.strip():return nodes
        self.adb.tap_node(find_by_id(nodes,'auto_stockcode'))
        nodes=self.wait(lambda ns:find_by_id(ns,'stock_search') is not None)
        fields=[n for n in nodes if n.resource_id.endswith('/auto_stockcode') and 'EditText' in n.class_name]
        if not fields:raise ThsError('搜索弹层缺少股票代码输入框')
        field=fields[0]
        self.adb.tap_node(field);self.adb.clear_text(len(field.text)+8);self.adb.input_text(code)
        def selected(ns):
            form=read_form(ns);name=find_by_id(ns,'stockname')
            if form and form.code==code and name and name.text.strip():return True
            rows=[n for n in ns if n.resource_id.endswith('/stockcode_tv') and n.text.strip()==code]
            if len(rows)==1:self.adb.tap_node(rows[0])
            return False
        return self.wait(selected)

    def fill(self,index,value,nodes=None):
        nodes=nodes if nodes is not None else self.snapshot();form=read_form(nodes)
        if not form:raise ThsError('表单结构已变化，未输入数量或价格')
        field=inputs(nodes)[index]
        if field.text.strip()==value:return False
        self.adb.tap_node(field);self.adb.clear_text(len(field.text)+8);self.adb.input_text(value)
        return True

    def preview(self,side,code,quantity,price=None):
        if type(quantity) is not int or quantity<=0:raise ValueError('委托数量必须为正整数')
        if price is not None:
            try:
                value=Decimal(str(price))
                if not value.is_finite() or value<=0:raise ValueError()
            except (ValueError,InvalidOperation):raise ValueError('委托价格无效') from None
        nodes=self.open(side);nodes=self.set_code(nodes,code)
        if price is not None and self.fill(0,str(price),nodes):nodes=None
        self.fill(1,str(quantity),nodes)
        nodes=self.wait(lambda ns:read_form(ns) is not None and read_form(ns).quantity==str(quantity))
        form=read_form(nodes)
        if form.code!=code or form.side!=side or (price is not None and Decimal(form.price)!=Decimal(str(price))):
            raise ThsError('同花顺预填参数核对失败，未发送委托')
        self.verify_account(nodes)
        self._last_form_nodes=nodes
        return form

    def clear_quantity(self):
        nodes=self.snapshot()
        if not read_form(nodes):raise ThsError('无法确认表单，未清理输入')
        field=inputs(nodes)[1];self.adb.tap_node(field);self.adb.clear_text(len(field.text)+8)
        self.wait(lambda ns:read_form(ns) is not None and not read_form(ns).quantity)

    def confirmation_required(self,nodes=None):
        nodes=nodes if nodes is not None else self.snapshot();gear=find_by_id(nodes,'quick_setting_image')
        if not gear:raise ThsError('找不到券商确认设置，禁止触碰委托按钮')
        self.adb.tap_node(gear)
        try:
            nodes=self.wait(lambda ns:any(n.text=='委托撤单免二次确认' for n in ns))
            return requires_confirmation(nodes)
        finally:
            current=self.snapshot();close=find_by_id(current,'iv_close')
            if not close or not close.enabled:raise ThsError('无法确认设置抽屉已关闭，禁止触碰委托按钮')
            self.adb.tap_node(close)
            self._last_form_nodes=self.wait(lambda ns:not any(n.text=='委托撤单免二次确认' for n in ns) and read_form(ns) is not None)

    def cancel_confirmation(self):
        nodes=self.snapshot();cancel=find_by_id(nodes,'cancel_btn')
        if not cancel or not cancel.enabled or cancel.text!='取消':
            raise ThsError('无法找到确认弹窗的取消按钮，请人工检查，禁止点击确认')
        self.adb.tap_node(cancel)
        self.wait(lambda ns:find_by_id(ns,'dialog_title') is None and read_form(ns) is not None)

    def submit(self,side,code,quantity,price=None,max_value=1000,dry_run=False,before_confirm=None):
        self._pending_plan=None
        self._last_form_nodes=None
        if not dry_run and before_confirm is None:raise ThsError('真实委托必须经过持久化请求入口')
        if not dry_run and not self.expected_account:raise ThsError('真实委托缺少已核验的资金账户')
        try:
            cap=Decimal(str(max_value)) if max_value is not None else None
            if cap is not None and (not cap.is_finite() or cap<=0):raise ValueError()
            if cap is None and price is None:raise ValueError()
        except (InvalidOperation,ValueError):raise ValueError('单笔金额上限必须为有效正数') from None
        form=self.preview(side,code,quantity,price)
        if not self.confirmation_required(self._last_form_nodes):
            raise ThsError('券商开启了免二次确认，已阻止委托；请先在券商内关闭该设置')
        nodes=self._last_form_nodes if self._last_form_nodes is not None else self.snapshot();current=read_form(nodes)
        if current!=form:raise ThsError('检查设置后委托表单已变化，未提交')
        self.verify_account(nodes)
        stock_name=find_by_id(nodes,'stockname')
        expected_name=stock_name.text.strip() if stock_name else ''
        if not expected_name:raise ThsError('委托表单缺少证券名称')
        self._pending_plan=Confirmation(side,code,expected_name,quantity,form.price)
        value=Decimal(form.price)*quantity
        if not value.is_finite() or value<=0 or (cap is not None and value>cap):raise ThsError('委托金额超过上限或价格无效')
        button=find_by_id(nodes,'btn_transaction')
        expected='买入' if side=='buy' else '卖出'
        labels=[n.text.replace(' ','') for n in nodes if n.text.strip() and button and button.bounds[0]<=n.center[0]<=button.bounds[2] and button.bounds[1]<=n.center[1]<=button.bounds[3]]
        if not button or not button.enabled or labels!=[expected]:raise ThsError('委托按钮与买卖方向不符')
        if not dry_run:before_confirm()
        self.adb.tap_node(button)
        nodes=self.wait(lambda ns:parse_confirmation(ns) is not None)
        confirmation=parse_confirmation(nodes)
        name=find_by_id(nodes,'stock_name_value').text.strip()
        mismatch=confirmation.side!=side or confirmation.code!=code or confirmation.quantity!=quantity or Decimal(confirmation.price)!=Decimal(form.price) or (cap is not None and Decimal(confirmation.price)*quantity>cap) or name.replace(' ','')!=expected_name.replace(' ','')
        try:self.verify_account(nodes)
        except Exception:
            self.cancel_confirmation()
            raise
        if mismatch:
            self.cancel_confirmation()
            raise ThsError('委托确认的方向、代码、价格或数量不符，已取消')
        if dry_run:
            self.cancel_confirmation()
            return dict(status='preview',submitted=False,confirm=asdict(confirmation))
        nodes=self.snapshot()
        if parse_confirmation(nodes)!=confirmation:
            raise ThsError('确认弹窗已变化，已停止')
        try:self.verify_account(nodes)
        except Exception:
            self.cancel_confirmation()
            raise
        ok=find_by_id(nodes,'ok_btn')
        if not ok or not ok.enabled or ok.text!='确认'+expected:raise ThsError('最终确认按钮无法核验')
        try:before_confirm()
        except Exception:
            self.cancel_confirmation()
            raise
        try:
            self.adb.tap_node(ok)
            nodes=self.wait(lambda ns:parse_result(ns) is not None,timeout=20)
            result=parse_result(nodes)
        except Exception:
            result=dict(status='unknown',submitted=False,message='提交结果未知，请核对券商委托，禁止直接重试')
        return dict(result,confirm=asdict(confirmation))

    def close(self):
        nodes=self.snapshot();back=find_by_id(nodes,'title_bar_left_container')
        if not back:raise ThsError('无法定位返回按钮，请人工返回交易主页')
        self.adb.tap_node(back)
