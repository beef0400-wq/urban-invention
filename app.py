from flask import Flask, request, abort
import os
import re
import json
import hmac
import base64
import hashlib
import random
import requests
from datetime import datetime, timedelta, timezone
from collections import Counter, defaultdict

app = Flask(__name__)

# ========= 環境變數 =========
CHANNEL_ACCESS_TOKEN = os.getenv("CHANNEL_ACCESS_TOKEN", "").strip()
CHANNEL_SECRET = os.getenv("CHANNEL_SECRET", "").strip()
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "1234").strip()
CRON_SECRET = os.getenv("CRON_SECRET", "aaa888").strip()
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

TZ_TW = timezone(timedelta(hours=8))

# ========= LINE =========
LINE_REPLY_URL = "https://api.line.me/v2/bot/message/reply"
LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"

# ========= 資料來源 =========
# 官方台彩最新開獎頁。若官方頁面格式改版，會自動嘗試備援來源。
SOURCE_539_OFFICIAL_LATEST = "https://www.taiwanlottery.com/lotto/lotto_lastest_result/"
SOURCE_539_OFFICIAL_4D = "https://www.taiwanlottery.com/lotto/result/4_d/"
SOURCE_539_FALLBACK = "https://zh.lottolyzer.com/result/taiwan/daily-cash-539"
SOURCE_BINGO_OFFICIAL = "https://www.taiwanlottery.com/lotto/result/bingo_bingo"

REQUEST_TIMEOUT = 8
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"

# ========= 通用工具 =========
def tw_now():
    return datetime.now(TZ_TW)

def fmt_nums(nums):
    return " ".join(f"{int(n):02d}" for n in nums)

def clean_text(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()

def safe_int(x, default=0):
    try:
        return int(x)
    except Exception:
        return default

def weighted_sample_without_replacement(items, weights, k):
    pool = [(x, max(float(weights.get(x, 0.01)), 0.01)) for x in items]
    out = []
    while pool and len(out) < k:
        total = sum(w for _, w in pool)
        r = random.uniform(0, total)
        acc = 0
        pick_i = 0
        for i, (x, w) in enumerate(pool):
            acc += w
            if acc >= r:
                pick_i = i
                break
        out.append(pool[pick_i][0])
        pool.pop(pick_i)
    return sorted(out)

def fetch_url(url):
    try:
        r = requests.get(
            url,
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.6"},
        )
        r.raise_for_status()
        # requests 通常可判斷；台彩若亂碼，保底用 apparent_encoding
        if not r.encoding or r.encoding.lower() == "iso-8859-1":
            r.encoding = r.apparent_encoding
        return r.text
    except Exception:
        return ""

# ========= LINE 驗證與回覆 =========
def verify_signature(body, signature):
    if not CHANNEL_SECRET:
        return True
    mac = hmac.new(CHANNEL_SECRET.encode("utf-8"), body, hashlib.sha256).digest()
    expected = base64.b64encode(mac).decode("utf-8")
    return hmac.compare_digest(expected, signature or "")

def reply_text(reply_token, text):
    if not CHANNEL_ACCESS_TOKEN:
        print("[LINE_REPLY]", text)
        return
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}",
    }
    payload = {
        "replyToken": reply_token,
        "messages": [{"type": "text", "text": text[:4900]}],
    }
    try:
        requests.post(LINE_REPLY_URL, headers=headers, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), timeout=REQUEST_TIMEOUT)
    except Exception as e:
        print("[reply_text error]", e)

# ========= 539 資料抓取 =========
def roc_to_ad_year(y):
    y = safe_int(y)
    if y < 1911:
        return y + 1911
    return y

def parse_date_any(s):
    s = str(s)
    patterns = [
        r"(\d{4})[./\-年](\d{1,2})[./\-月](\d{1,2})",
        r"(\d{3})[./\-年](\d{1,2})[./\-月](\d{1,2})",
    ]
    for p in patterns:
        m = re.search(p, s)
        if m:
            y, mo, d = map(int, m.groups())
            y = roc_to_ad_year(y)
            try:
                return datetime(y, mo, d, tzinfo=TZ_TW).date()
            except Exception:
                pass
    return None

def extract_number_groups(text):
    """
    從頁面文字中抓 1~39 的 5 顆號碼群。
    回傳 list[list[int]]
    """
    groups = []
    # 常見格式：01 02 03 04 05 / 1 2 3 4 5
    candidates = re.findall(r"(?:\b(?:0?[1-9]|[12]\d|3[0-9])\b[\s,，、|／/.-]*){5,}", text)
    for c in candidates:
        nums = [safe_int(x) for x in re.findall(r"\b(?:0?[1-9]|[12]\d|3[0-9])\b", c)]
        # 以每5顆切一組，避免吃到頁面選單雜訊
        for i in range(0, len(nums), 5):
            g = nums[i:i+5]
            if len(g) == 5 and len(set(g)) == 5 and all(1 <= n <= 39 for n in g):
                groups.append(sorted(g))
    # 去重但保留順序
    out = []
    seen = set()
    for g in groups:
        key = tuple(g)
        if key not in seen:
            seen.add(key)
            out.append(g)
    return out

def parse_539_from_lottolyzer(html):
    """
    解析 lottolyzer 備援頁。
    """
    text = clean_text(re.sub(r"<[^>]+>", " ", html))
    draws = []

    # 嘗試抓：第115000123期 2026年05月20日 01 02 03 04 05
    pattern = re.compile(
        r"第\s*(\d{6,})\s*期.{0,80}?(\d{4}年\d{1,2}月\d{1,2}日).{0,120}?((?:\b(?:0?[1-9]|[12]\d|3[0-9])\b\s*){5})"
    )
    for m in pattern.finditer(text):
        issue = m.group(1)
        d = parse_date_any(m.group(2))
        nums = [safe_int(x) for x in re.findall(r"\b(?:0?[1-9]|[12]\d|3[0-9])\b", m.group(3))]
        if d and len(nums) == 5 and len(set(nums)) == 5:
            draws.append({"date": d, "issue": issue, "nums": sorted(nums), "source": "備援資料"})

    # 若格式變動，退而求其次：用日期附近的號碼群
    if not draws:
        dates = [(m.start(), parse_date_any(m.group(0))) for m in re.finditer(r"\d{4}年\d{1,2}月\d{1,2}日", text)]
        for pos, d in dates[:30]:
            if not d:
                continue
            chunk = text[pos:pos+250]
            groups = extract_number_groups(chunk)
            if groups:
                draws.append({"date": d, "issue": "", "nums": groups[0], "source": "備援資料"})

    # 日期新到舊
    draws = sorted(draws, key=lambda x: x["date"], reverse=True)
    return dedupe_draws(draws)

def parse_539_from_official(html):
    """
    官方頁面格式常有前端渲染/改版，所以採保守解析：
    只接受含「今彩539 / Daily Cash / 539」附近區塊出現的 5 顆號碼。
    """
    raw = html
    text = clean_text(re.sub(r"<[^>]+>", " ", raw))
    draws = []

    key_positions = [m.start() for m in re.finditer(r"(今彩\s*539|Daily\s*Cash|539)", text, flags=re.I)]
    for pos in key_positions[:20]:
        chunk = text[max(0, pos-300):pos+1000]
        d = parse_date_any(chunk) or tw_now().date()
        issue_m = re.search(r"(?:第)?\s*(\d{6,})\s*(?:期)?", chunk)
        issue = issue_m.group(1) if issue_m else ""
        groups = extract_number_groups(chunk)
        for g in groups[:3]:
            draws.append({"date": d, "issue": issue, "nums": g, "source": "官方台彩"})

    return dedupe_draws(sorted(draws, key=lambda x: x["date"], reverse=True))

def dedupe_draws(draws):
    out = []
    seen = set()
    for d in draws:
        key = (str(d.get("date")), tuple(d.get("nums", [])))
        if key in seen:
            continue
        if len(d.get("nums", [])) == 5:
            seen.add(key)
            out.append(d)
    return out

def get_539_draws(limit=40):
    """
    取得最新 539 開獎資料。
    優先官方，官方解析不足時改用備援。
    """
    draws = []

    for url in [SOURCE_539_OFFICIAL_LATEST, SOURCE_539_OFFICIAL_4D]:
        html = fetch_url(url)
        if html:
            draws += parse_539_from_official(html)

    draws = dedupe_draws(draws)

    # 官方抓不到足夠近期資料就用備援補足
    if len(draws) < 10:
        html = fetch_url(SOURCE_539_FALLBACK)
        if html:
            draws += parse_539_from_lottolyzer(html)

    draws = dedupe_draws(sorted(draws, key=lambda x: x["date"], reverse=True))
    return draws[:limit]

# ========= 539 AI 動態母盤 =========
def zone(n):
    if 1 <= n <= 13:
        return "低區"
    if 14 <= n <= 26:
        return "中區"
    return "高區"

def tail(n):
    return n % 10

def build_539_ai_board(draws):
    """
    新版核心：
    - 母盤只吃最新資料，避免卡死舊盤。
    - 近1/3/5/10期權重提高。
    - 保留昨日重號 1~2 顆。
    - 加入髒盤/偏區/連號/重尾，避免盤面過度工整。
    """
    all_nums = list(range(1, 40))
    now_date = tw_now().date()

    if not draws:
        # 沒資料時才使用保底盤，且明確標記
        base = sorted(random.sample(all_nums, 12))
        return {
            "stale": True,
            "latest": None,
            "source": "無法取得資料，使用臨時盤",
            "mother": base,
            "stable2": sorted(base[:6]),
            "main3": sorted(base[2:8]),
            "boom4": sorted(base[4:12]),
            "dirty": sorted(random.sample(all_nums, 8)),
            "hot": [],
            "cold": [],
            "zones": {},
            "tails": {},
            "strategy": "資料源暫時失效：此盤只做臨時參考，請先確認台彩資料是否可抓取。",
        }

    latest = draws[0]
    latest_date = latest["date"]
    age_days = (now_date - latest_date).days
    stale = age_days > 3

    weights = defaultdict(float)

    # 近1期：重號核心，不排除昨天號
    for n in latest["nums"]:
        weights[n] += 5.0

    # 近3期：短節奏
    for d in draws[:3]:
        for n in d["nums"]:
            weights[n] += 3.6

    # 近5期：延伸節奏
    for d in draws[:5]:
        for n in d["nums"]:
            weights[n] += 2.4

    # 近10期：熱區
    for d in draws[:10]:
        for n in d["nums"]:
            weights[n] += 1.5

    # 冷號回補：最近10期沒開，但近40期有動過者加權
    recent10 = set(n for d in draws[:10] for n in d["nums"])
    recent40_counter = Counter(n for d in draws[:40] for n in d["nums"])
    cold_candidates = [n for n in all_nums if n not in recent10]
    for n in cold_candidates:
        weights[n] += 0.8
        if recent40_counter[n] >= 2:
            weights[n] += 0.5

    # 頭尾/區段偏移：避免全平均盤
    tail_counter = Counter(tail(n) for d in draws[:10] for n in d["nums"])
    zone_counter = Counter(zone(n) for d in draws[:10] for n in d["nums"])
    hot_tails = [t for t, _ in tail_counter.most_common(3)]
    hot_zones = [z for z, _ in zone_counter.most_common(2)]

    for n in all_nums:
        if tail(n) in hot_tails:
            weights[n] += 0.45
        if zone(n) in hot_zones:
            weights[n] += 0.35
        # 隨機擾動，避免每天盤型死板
        weights[n] += random.uniform(0, 0.75)

    hot_nums = [n for n, _ in Counter(n for d in draws[:10] for n in d["nums"]).most_common(10)]
    cold_nums = sorted(cold_candidates, key=lambda n: (recent40_counter[n], random.random()), reverse=True)[:10]

    # 母盤 12 顆：顆數提高
    mother = weighted_sample_without_replacement(all_nums, weights, 12)

    # 強制帶入昨日 1~2 顆，提升重號機率
    repeat_keep = random.sample(latest["nums"], k=min(random.choice([1, 2]), len(latest["nums"])))
    mother_set = set(mother) | set(repeat_keep)
    while len(mother_set) > 12:
        removable = [n for n in mother_set if n not in repeat_keep]
        if not removable:
            break
        mother_set.remove(min(removable, key=lambda n: weights[n]))
    while len(mother_set) < 12:
        add = weighted_sample_without_replacement([n for n in all_nums if n not in mother_set], weights, 1)
        if add:
            mother_set.add(add[0])
    mother = sorted(mother_set)

    # 2星穩定：抓高權重 + 昨日重號
    stable2 = sorted(set(weighted_sample_without_replacement(mother, weights, 7)) | set(repeat_keep))
    stable2 = sorted(stable2)[:8]

    # 3星主攻：中高權重，不要太平均
    main3 = weighted_sample_without_replacement(mother, weights, 8)

    # 4星爆發：母盤大顆數，加入冷號與偏區
    boom_pool = sorted(set(mother + cold_nums[:4] + hot_nums[:4]))
    boom4 = weighted_sample_without_replacement(boom_pool, weights, 10)

    # 髒盤：偏區、連號、重尾
    zpick = random.choice(["低區", "中區", "高區"])
    zone_pool = [n for n in all_nums if zone(n) == zpick]
    start = random.randint(1, 35)
    seq_pool = [n for n in range(start, min(40, start + 5))]
    tail_pick = random.choice(hot_tails or list(range(10)))
    tail_pool = [n for n in all_nums if tail(n) == tail_pick]
    dirty_pool = sorted(set(zone_pool + seq_pool + tail_pool + latest["nums"]))
    dirty_weights = defaultdict(float, weights)
    for n in dirty_pool:
        dirty_weights[n] += random.uniform(0.5, 2.0)
    dirty = weighted_sample_without_replacement(dirty_pool, dirty_weights, 8)

    # 結構摘要
    zc = Counter(zone(n) for n in mother)
    tc = Counter(tail(n) for n in mother)

    return {
        "stale": stale,
        "latest": latest,
        "source": latest.get("source", ""),
        "mother": mother,
        "stable2": stable2,
        "main3": main3,
        "boom4": boom4,
        "dirty": dirty,
        "hot": hot_nums[:8],
        "cold": cold_nums[:8],
        "zones": dict(zc),
        "tails": dict(tc.most_common(5)),
        "strategy": "母盤改為近1/3/5/10期動態權重；保留昨日重號，加入冷號回補、偏區、連號、重尾與隨機擾動。",
    }

def render_539_ai():
    draws = get_539_draws(limit=40)
    board = build_539_ai_board(draws)

    latest = board["latest"]
    today = tw_now().strftime("%Y.%m.%d")

    if latest:
        latest_line = f"{latest['date'].strftime('%Y.%m.%d')}｜第{latest.get('issue') or '-'}期｜{fmt_nums(latest['nums'])}"
        age = (tw_now().date() - latest["date"]).days
    else:
        latest_line = "資料取得失敗"
        age = 999

    stale_note = ""
    if board["stale"]:
        stale_note = "\n⚠️ 資料警示：最新資料不是近期開獎，系統已停止使用舊母盤，只輸出臨時盤。"

    zones = board["zones"]
    zone_line = f"低{zones.get('低區',0)}｜中{zones.get('中區',0)}｜高{zones.get('高區',0)}"
    tails = board["tails"]
    tail_line = "・".join(f"{k}尾x{v}" for k, v in tails.items()) or "-"

    text = f"""【今日539 AI母盤】{stale_note}

■ 最新資料
{latest_line}
資料年齡：{age}天
資料源：{board['source']}

■ 動態母盤 12顆
{fmt_nums(board['mother'])}

■ 主軸號｜2星穩定
{fmt_nums(board['stable2'])}

■ 3星主攻
{fmt_nums(board['main3'])}

■ 4星爆發
{fmt_nums(board['boom4'])}

■ 髒盤補位
{fmt_nums(board['dirty'])}

■ 熱號追蹤
{fmt_nums(board['hot'])}

■ 冷號回補
{fmt_nums(board['cold'])}

■ 結構分析
區段：{zone_line}
強尾：{tail_line}

■ 策略解讀
2星：優先用主軸號，保留1~2顆昨日重號。
3星：主攻不要只押平均盤，需搭配連號/重尾。
4星：用爆發盤放大波動，髒盤做補位。

■ AI陪跑記錄
節奏比準度重要。
本版已移除固定舊母盤，改用每日動態母盤。

（數據結構參考，非保證）"""
    return text[:4900]

# ========= Bingo 簡易真實資料抓取/分析 =========
def parse_bingo_latest(html):
    text = clean_text(re.sub(r"<[^>]+>", " ", html))
    # Bingo 1~80，取最近一組 20 顆
    nums = [safe_int(x) for x in re.findall(r"\b(?:[1-9]|[1-7]\d|80)\b", text)]
    # 避免抓到年月日/期數，找連續20顆 1~80 且不重複
    for i in range(0, max(0, len(nums)-20)):
        g = nums[i:i+20]
        if len(g) == 20 and len(set(g)) == 20 and all(1 <= n <= 80 for n in g):
            return sorted(g)
    return []

def render_bingo_ai(periods=1):
    html = fetch_url(SOURCE_BINGO_OFFICIAL)
    latest = parse_bingo_latest(html) if html else []
    if not latest:
        pick = sorted(random.sample(range(1, 81), 10))
        return f"""【Bingo AI分析】

⚠️ 官方資料暫時解析失敗，以下為臨時盤。
建議號：{fmt_nums(pick)}

（數據結構參考，非保證）"""

    low = [n for n in latest if n <= 40]
    high = [n for n in latest if n > 40]
    odd = [n for n in latest if n % 2 == 1]
    even = [n for n in latest if n % 2 == 0]
    pool = latest[:]
    extra = random.sample([n for n in range(1,81) if n not in pool], 20)
    weights = defaultdict(lambda: 1.0)
    for n in latest:
        weights[n] += 3.0
    for n in extra:
        weights[n] += random.uniform(0.2, 1.2)

    suggest = weighted_sample_without_replacement(sorted(set(pool + extra)), weights, 10)

    return f"""【Bingo AI分析】

■ 最新官方盤
{fmt_nums(latest)}

■ 結構
低區：{len(low)}｜高區：{len(high)}
單：{len(odd)}｜雙：{len(even)}

■ 建議觀察號 10顆
{fmt_nums(suggest)}

■ 策略
短期以最新盤重複與鄰近補位為主。
不建議追高倍投。

（數據結構參考，非保證）"""

# ========= 指令處理 =========
def help_text():
    return """【AI陪跑指令】

539：
輸入 539
輸入 539分析
輸入 /預測

賓果：
輸入 賓果
輸入 1期 / 5期 / 10期

其他：
輸入 help 查看指令

（所有分析皆為數據結構參考，非保證）"""

def handle_text(user_text):
    t = clean_text(user_text)

    if not t:
        return help_text()

    low = t.lower()

    if low in ["help", "說明", "指令", "/help"]:
        return help_text()

    # 539
    if t in ["539", "今彩539", "539分析", "今日539", "今日539 AI母盤", "母盤", "/預測", "預測"]:
        return render_539_ai()

    # Bingo
    if t in ["賓果", "bingo", "Bingo", "賓果分析"]:
        return render_bingo_ai(1)

    if t in ["1期", "5期", "10期"]:
        return render_bingo_ai(safe_int(t.replace("期", ""), 1))

    return help_text()

# ========= Flask Routes =========
@app.route("/", methods=["GET"])
def index():
    return "AI LINE Bot is running."

@app.route("/health", methods=["GET"])
def health():
    return {
        "ok": True,
        "time": tw_now().isoformat(),
        "line_token": bool(CHANNEL_ACCESS_TOKEN),
        "line_secret": bool(CHANNEL_SECRET),
    }

@app.route("/test539", methods=["GET"])
def test539():
    return "<pre>" + render_539_ai() + "</pre>"

@app.route("/callback", methods=["POST"])
def callback():
    body = request.get_data()
    signature = request.headers.get("X-Line-Signature", "")
    if not verify_signature(body, signature):
        abort(400)

    try:
        data = json.loads(body.decode("utf-8"))
    except Exception:
        abort(400)

    for event in data.get("events", []):
        if event.get("type") != "message":
            continue
        msg = event.get("message", {})
        if msg.get("type") != "text":
            continue
        reply_token = event.get("replyToken")
        user_text = msg.get("text", "")
        answer = handle_text(user_text)
        if reply_token:
            reply_text(reply_token, answer)

    return "OK"

# 兼容舊 webhook 路徑
@app.route("/webhook", methods=["POST"])
def webhook():
    return callback()

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
