"""Bark sends only after explicit configuration; secrets kept in OS credential store."""
import json,time
from datetime import datetime
from .provider import now_cn,CN
from urllib.request import Request,urlopen

SERVICE='com.xreddot.stockmonitor.bark'

def key(value=None):
    import keyring
    if value is not None:
        if value: keyring.set_password(SERVICE,'device',value.strip())
        else: keyring.delete_password(SERVICE,'device')
    return keyring.get_password(SERVICE,'device')

def bark(title,body):
    secret=key()
    if not secret: raise ValueError('请先填写 Bark 推送密钥')
    request=Request('https://api.day.app/push',data=json.dumps(dict(device_key=secret,title=title,
        body=body,group='观量',sound='minuet')).encode(),headers={'Content-Type':'application/json'},method='POST')
    with urlopen(request,timeout=10) as response: result=json.load(response)
    if result.get('code')!=200: raise ValueError('Bark 服务未接受推送，请检查密钥及服务状态')
    return {'status':'accepted','message':'推送服务已接受，请在 iPhone 上确认；不代表已送达'}

def drain(store,enabled):
    if not enabled: return
    for row in store.query("SELECT d.*,e.payload FROM delivery d JOIN events e USING(key) WHERE status IN ('pending','retry') AND next_try<=?",(time.time(),)):
        e=json.loads(row['payload'])
        stamp=datetime.fromisoformat(e['trading_date']+'T'+e['event_label']).replace(tzinfo=CN)
        if (now_cn()-stamp).total_seconds()>180:
            store.execute("UPDATE delivery SET status='expired' WHERE key=?",(row['key'],))
            continue
        attempts=row['attempts']+1
        try:
            e=json.loads(row['payload'])
            bark(e.get('notification_title','卖点规则提醒 · '+e['symbol']),e.get('notification_body',f"{e['symbol']} {e['event_label']}；仅提醒，手动交易。"))
            status='accepted'
        except Exception:
            status='failed' if attempts>=3 else 'retry'
        store.execute('UPDATE delivery SET status=?,attempts=?,next_try=? WHERE key=?',
            (status,attempts,time.time()+min(300,10*2**attempts),row['key']))
