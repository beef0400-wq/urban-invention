"""Independent application identity, unrelated to external service accounts."""
import hashlib, json, re
import store, membership
PREFIX = 'suying:account:'

def ensure(uid):
    code = 'SY-' + hashlib.sha256(('suying-account-v1:' + uid).encode()).hexdigest()[:12].upper()
    key = PREFIX + code
    with store.cursor(True) as c:
        c.execute('INSERT INTO v2_state VALUES (%s,%s) ON CONFLICT(user_id) DO NOTHING',
                  (key, json.dumps({'uid': uid, 'created_at': membership.now_tw().isoformat()})))
        c.execute('SELECT payload FROM v2_state WHERE user_id=%s', (key,))
        if json.loads(c.fetchone()[0])['uid'] != uid:
            raise RuntimeError('帳號建立衝突，請聯絡管理員。')
    return code

def resolve(code):
    code = str(code).strip().upper()
    if not re.fullmatch(r'SY-[A-F0-9]{12}', code):
        return store.get_state('suying:username:' + code.lower()).get('uid')
    return store.get_state(PREFIX + code).get('uid')

def profile(uid):
    code = ensure(uid)
    status, expiry = membership.get_status(uid)
    if status=='FREE':
        trial_expiry=membership._membership_row(uid).get('trial_expires_at')
        if trial_expiry and trial_expiry<=membership.now_tw():status,expiry='EXPIRED',trial_expiry
    username=store.get_state(PREFIX+code).get('username')
    return {'code': code, 'username':username, 'trial_available':not username and not membership.has_used_trial(uid) and status!='PAID', 'trial_active':status=='TRIAL', 'status': {'PAID':'已開通','TRIAL':'試用中','EXPIRED':'已到期','FREE':'待開通'}[status],
            'expires_at': expiry.astimezone(membership.TZ_TW).isoformat() if expiry else None,
            'access': status in ('PAID','TRIAL')}

def recent(limit=10):
    with store.cursor() as c:
        c.execute('SELECT user_id,payload FROM v2_state WHERE user_id LIKE %s ORDER BY user_id LIMIT %s', (PREFIX+'%',100))
        rows=c.fetchall()
    rows.sort(key=lambda row:json.loads(row[1]).get('created_at',''),reverse=True)
    return [(key[len(PREFIX):],json.loads(payload)['uid']) for key,payload in rows[:limit]]

SUCCESS = '綁定完成！請回小幫手驗證開通。\n將此帳號提供給小幫手，管理員確認後即可開通。'

def validate_username(value):
    name=str(value).strip()
    if not re.fullmatch(r'[A-Za-z0-9_]{4,20}',name):
        raise ValueError('帳號請使用4～20個英文字母、數字或底線。')
    return name

def bind(uid,value):
    name=validate_username(value);code=ensure(uid)
    with store.cursor(True) as c:
        c.execute('SELECT payload FROM v2_state WHERE user_id=%s',(PREFIX+code,))
        data=json.loads(c.fetchone()[0])
        if data.get('username'):
            if data['username'].lower()!=name.lower():raise ValueError('帳號已綁定。如需更換，請聯絡小幫手。')
            return data['username']
        key='suying:username:'+name.lower()
        c.execute('INSERT INTO v2_state VALUES (%s,%s) ON CONFLICT(user_id) DO NOTHING',(key,json.dumps({'uid':uid})))
        c.execute('SELECT payload FROM v2_state WHERE user_id=%s',(key,))
        if json.loads(c.fetchone()[0])['uid']!=uid:raise ValueError('此帳號已被綁定，請確認帳號或聯絡小幫手。')
        data.update(username=name,bound_at=membership.now_tw().isoformat())
        c.execute('UPDATE v2_state SET payload=%s WHERE user_id=%s',(json.dumps(data),PREFIX+code))
    return name

def trial_buttons(uid):
    return [('免費試用1小時','免費體驗')] if profile(uid)['trial_available'] else []

def access_notice(uid):
    if membership.has_used_trial(uid):
        return '免費試用已到期。請完成註冊、綁定帳號，再回小幫手驗證開通。'
    if profile(uid)['username']:return '帳號已綁定，請回小幫手驗證開通。'
    return '請先開啟免費試用1小時，或綁定帳號後回小幫手驗證開通。'
