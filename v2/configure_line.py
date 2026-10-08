"""Owner-authorized one-time connection of @957ridwt to isolated V2.
Uses server-held credentials, stores previous endpoint for reversible rollback.
"""
import os, json
import requests
from deployment_preflight import validate_database_url
validate_database_url(os.environ.get('DATABASE_URL',''))
import store
TARGET = 'https://ai-rational-companion-v1-test.onrender.com/webhook'
EXPECTED_BOT = '@957ridwt'
KEY = '__v2_line_connection__'
BASE = 'https://api.line.me/v2/bot'
token = os.getenv('CHANNEL_ACCESS_TOKEN') or os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
if not token:
    raise RuntimeError('LINE connection: missing server token')
headers = {'Authorization':'Bearer '+token,'Content-Type':'application/json'}

def call(method,path,body=None):
    response=requests.request(method,BASE+path,headers=headers,json=body,timeout=90)
    if response.status_code != 200:
        raise RuntimeError('LINE connection HTTP '+str(response.status_code)+' on '+path)
    return response.json()

info=call('GET','/info')
if info.get('basicId') != EXPECTED_BOT:
    raise RuntimeError('Refusing to change an unapproved LINE account')
current=call('GET','/channel/webhook/endpoint')
saved=store.get_state(KEY)
if not saved:
    saved={'previous_endpoint':current.get('endpoint'),'previous_active':current.get('active'),'approved_bot':EXPECTED_BOT,'target':TARGET,'connected':False}
    store.put_state(KEY,saved)
if saved.get('connected') and current.get('endpoint')==TARGET:
    print('V2_LINE_CONNECTION already verified',flush=True)
else:
    try:
        call('PUT','/channel/webhook/endpoint',{'endpoint':TARGET})
        updated=call('GET','/channel/webhook/endpoint')
        if updated.get('endpoint') != TARGET or not updated.get('active'):
            raise RuntimeError('LINE endpoint or active status verification failed')
        test=call('POST','/channel/webhook/test',{'endpoint':TARGET})
        if test.get('success') is not True or test.get('statusCode') != 200:
            raise RuntimeError('LINE webhook verification failed: '+str(test.get('statusCode')))
        saved['connected']=True
        saved['verified_at']=__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()
        saved['test_status']=test.get('statusCode')
        store.put_state(KEY,saved)
        print('V2_LINE_CONNECTION PASS '+json.dumps({'basic_id':EXPECTED_BOT,'endpoint':TARGET,'active':True,'line_test_success':True,'statusCode':test.get('statusCode')},ensure_ascii=False),flush=True)
    except Exception:
        if saved.get('previous_endpoint') and current.get('endpoint') != TARGET:
            call('PUT','/channel/webhook/endpoint',{'endpoint':saved['previous_endpoint']})
            print('V2_LINE_CONNECTION restored prior endpoint',flush=True)
        raise
