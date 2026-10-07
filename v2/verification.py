"""Immutable pre-draw 539 forecasts, exact-date reconciliation. No hindsight backfill."""
import json, hashlib
from datetime import datetime, time
import store
from legacy import lotto539 as engine

def locked_pack(target):
    with store.cursor() as c:
        c.execute('SELECT payload FROM v2_public_539 WHERE target_date=%s',(target.isoformat(),));r=c.fetchone()
    return json.loads(r[0]) if r else None

def lock(pack, target=None, now=None):
    now=now or engine.now_tw();target=target or now.date()
    old=locked_pack(target)
    if old: return old
    # Conservatively close before the evening draw; Sunday has no 539 draw.
    if target.weekday()==6 or now.date()>target or (now.date()==target and now.time().replace(tzinfo=None)>=time(20,0)):
        raise ValueError('今日鎖盤時間已過或休市；沒有開獎前鎖定分析，不補做事後預測。')
    model=json.loads(pack['note']);latest=model.get('latest_draw_date')
    if not model.get('data_fresh') or not latest or latest>=target.isoformat():
        raise ValueError('歷史資料無法確認為開獎前資料，暫停產生今日分析。')
    body=json.dumps(pack,sort_keys=True,ensure_ascii=False)
    digest=hashlib.sha256(body.encode()).hexdigest()
    with store.cursor(True) as c:
        c.execute('INSERT INTO v2_public_539(target_date,locked_at,digest,payload) VALUES (%s,%s,%s,%s) ON CONFLICT(target_date) DO NOTHING',(target.isoformat(),now.isoformat(),digest,body))
    return locked_pack(target)

def reconcile(draws):
    count=0
    with store.cursor(True) as c:
        for d,nums in draws:
            if len(set(nums))!=5 or any(n<1 or n>39 for n in nums): continue
            c.execute('UPDATE v2_public_539 SET actual=%s,verified_at=%s WHERE target_date=%s AND actual IS NULL',(json.dumps(sorted(nums)),engine.now_tw().isoformat(),d.isoformat()))
        c.execute('SELECT target_date,payload,actual FROM v2_public_539 WHERE actual IS NOT NULL ORDER BY target_date DESC')
        rows=c.fetchall()
    # Preserve legacy model_results semantics for recovery model; only exact locked forecasts.
    for d,p,a in rows:
        m=json.loads(json.loads(p)['note']);actual=json.loads(a)
        hit=len(set(engine.parse_nums_text(m['motherboard']))&set(actual))
        with engine.db_cursor(commit=True) as c:
            c.execute('INSERT INTO model_results (result_date,motherboard,actual_numbers,hit_count,created_at) VALUES (%s,%s,%s,%s,%s) ON CONFLICT(result_date) DO NOTHING',(d,m['motherboard'],engine.fmt_nums(actual),hit,engine.now_tw()))
        count+=1
    return count

def report(limit=7):
    limit=limit if limit in (7,30,90) else 7
    with store.cursor() as c:
        c.execute('SELECT target_date,locked_at,digest,payload,actual FROM v2_public_539 ORDER BY target_date DESC LIMIT %s',(limit,));rows=c.fetchall()
    lines=[f'539 公開驗證｜最近 {limit} 期','只列開獎前鎖定分析；成功、失敗與待開獎均保留。']
    for d,at,digest,p,a in rows:
        m=json.loads(json.loads(p)['note']); lines.append(f'\n{d}｜鎖定 {at}\n母盤 {m["motherboard"]}\n驗證碼 {digest[:12]}')
        if a is None: lines.append('待開獎／待資料更新');continue
        actual=set(json.loads(a));lines.append('開獎 '+engine.fmt_nums(actual))
        for key,n in [('motherboard',0),('stable2',2),('attack3',3),('burst4',4)]:
            hits=len(set(engine.parse_nums_text(m[key]))&actual)
            from math import comb
            lines.append(f'{"母盤" if not n else str(n)+"星"}命中 {hits} 顆'+('' if not n else f'｜中獎組合 {comb(hits,n) if hits>=n else 0}'))
    return '\n'.join(lines) if rows else '\n'.join(lines+['尚無開獎前鎖定資料，不回填歷史預測。'])
