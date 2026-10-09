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
    if not re.fullmatch(r'SY-[A-F0-9]{12}', code): return None
    return store.get_state(PREFIX + code).get('uid')

def profile(uid):
    code = ensure(uid)
    status, expiry = membership.get_status(uid)
    if status=='FREE':
        trial_expiry=membership._membership_row(uid).get('trial_expires_at')
        if trial_expiry and trial_expiry<=membership.now_tw():status,expiry='EXPIRED',trial_expiry
    return {'code': code, 'status': {'PAID':'已開通','TRIAL':'試用中','EXPIRED':'已到期','FREE':'待開通'}[status],
            'expires_at': expiry.astimezone(membership.TZ_TW).isoformat() if expiry else None,
            'access': status in ('PAID','TRIAL')}

def recent(limit=10):
    with store.cursor() as c:
        c.execute('SELECT user_id,payload FROM v2_state WHERE user_id LIKE %s ORDER BY user_id LIMIT %s', (PREFIX+'%',100))
        rows=c.fetchall()
    rows.sort(key=lambda row:json.loads(row[1]).get('created_at',''),reverse=True)
    return [(key[len(PREFIX):],json.loads(payload)['uid']) for key,payload in rows[:limit]]
