"""Free test-runtime verification. Sleeping services catch up when awakened.
No forecasts are created after the pre-draw cutoff. For guaranteed production
uptime use an external scheduler; this test runner does not claim that guarantee.
"""
import os, threading, logging
from datetime import datetime
import store, verification
from legacy import lotto539 as engine
_STARTED = False
_LOCK = threading.Lock()


def tick(now=None):
    now = now or engine.now_tw()
    if now.hour < 18:
        return
    state = store.get_state('__v2_verification_scheduler__')
    last = state.get('last_attempt')
    if last and (now - datetime.fromisoformat(last)).total_seconds() < 300:
        return
    store.put_state('__v2_verification_scheduler__', {'last_attempt': now.isoformat()})
    if now.weekday() != 6 and 18 <= now.hour < 20 and not verification.locked_pack(now.date()):
        engine.get_or_build_today_pick_539()
        logging.info('V2_SCHEDULE_LOCK completed')
    if now.hour >= 21:
        engine.ensure_latest_539_in_db()
        count = verification.reconcile(engine.load_539_draws(240))
        logging.info('V2_SCHEDULE_RECONCILE completed forecasts=%s', count)


def start():
    global _STARTED
    if os.getenv('RENDER_SERVICE_ID') != 'srv-dami3j740ujc73b1acfg':
        return False
    with _LOCK:
        if _STARTED:
            return True
        _STARTED = True
        def loop():
            stop = threading.Event()
            while True:
                try:
                    tick()
                except Exception:
                    logging.exception('V2_SCHEDULE_ERROR')
                stop.wait(60)
        threading.Thread(target=loop, name='v2-test-verification', daemon=True).start()
    return True
