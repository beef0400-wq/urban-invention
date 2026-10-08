"""Shared native LINE Flex presentation; never changes model data or commands."""
import json
import re

INK='#15243B'; MUTED='#66768B'; BG='#F3F6FA'
THEMES={'baccarat':('百家實戰','#2478B8','路單觀察 · 多訊號分析'),
        '539':('539 好懂看盤','#087F78','每日模型 · 開獎追蹤'),
        'bingo':('賓果看盤','#7255C6','即時資料 · 趨勢觀察'),
        'member':('會員中心','#405A7A','一個會員 · 三種模式'),
        'home':('甦贏','#405A7A','看數據 · 看懂再上場')}

def txt(text,size='sm',color=INK,bold=False):
    node={'type':'text','text':str(text) or '—','size':size,'color':color,'wrap':True,'flex':0}
    if bold:node['weight']='bold'
    return node

def theme(text):
    first=text.split('\n',1)[0]
    if '會員' in first or '體驗' in first:return 'member'
    if '539' in first or '母盤' in first or '驗證' in first:return '539'
    if 'Bingo' in first or '賓果' in first:return 'bingo'
    if any(k in first for k in ('百家','詳細分析','辨識','匯入','牌路')):return 'baccarat'
    return 'home'

def public_text(text):
    # Names are translated only for display. Event actions keep internal commands.
    return str(text).replace('AI 理性陪跑','甦贏').replace('AI理性陪跑','甦贏').replace('百家 AI','百家實戰').replace('539 AI','539 好懂看盤').replace('Bingo AI','賓果看盤').replace('莊','紅').replace('閒','藍').replace('baccarat','百家').replace('bingo','賓果')

def action(label,value):
    return {'type':'uri','label':public_text(label)[:20],'uri':value} if value.startswith('https://') else {'type':'message','label':public_text(label)[:20],'text':value}

def button(label,value,color,primary=False):
    return {'type':'button','style':'primary' if primary else 'secondary','height':'sm',
            **({'color':color} if primary else {}),
            'action':action(label,value),'flex':1}

def footer(items,color):
    rows=[]
    items=list(dict.fromkeys(tuple(x) for x in (items or [])))[:13]
    # Keep actual round actions on a single visible row.
    results=[x for x in items if x[1] in ('莊','閒','和')]
    if len(results)==3:
        colors={'莊':'#D55362','閒':'#2478B8','和':'#138875'}
        rows.append({'type':'box','layout':'horizontal','spacing':'sm','contents':[button(a,b,colors[b],True) for a,b in results]})
        items=[x for x in items if x not in results]
    for i in range(0,len(items),2):
        rows.append({'type':'box','layout':'horizontal','spacing':'sm',
                     'contents':[button(a,b,color,i==0 and j==0 and not results) for j,(a,b) in enumerate(items[i:i+2])]})
    return {'type':'box','layout':'vertical','spacing':'sm','paddingAll':'16px','contents':rows or [txt('可直接輸入指令','xs',MUTED)]}

def section(lines,color):
    nodes=[]
    for i,line in enumerate(lines):
        line=line.strip()
        if not line:continue
        # Number-only lines get readable, evenly spaced chips; no number is dropped.
        if re.fullmatch(r'\d{1,2}(?:[\s、,，]+\d{1,2})+',line):
            nums=re.findall(r'\d{1,2}',line)
            for start in range(0,len(nums),5):
                nodes.append({'type':'box','layout':'horizontal','spacing':'sm','contents':[
                    {'type':'box','layout':'vertical','backgroundColor':BG,'cornerRadius':'8px','paddingAll':'8px',
                     'flex':1,'contents':[dict(txt(n,'md',color,True),align='center')]} for n in nums[start:start+5]]})
        elif '綜合判讀：' in line:
            nodes.extend([txt('本輪觀察','xs',MUTED),txt(line.split('綜合判讀：',1)[1],'xxl',color,True)])
        elif '訊號指數：' in line:
            nodes.append(txt(line,'lg',color,True))
        else:
            headline=i==0 and (len(line)<28 or line.startswith(('▍','📊','🎯','⭐','🔥','🧩','📌','近')))
            nodes.append(txt(line,'md' if headline else 'sm',color if headline else INK,headline))
    return {'type':'box','layout':'vertical','spacing':'sm','backgroundColor':'#FFFFFF',
            'cornerRadius':'12px','paddingAll':'14px','contents':nodes or [txt('—')]}

def sections(text):
    text=re.sub(r'\n(?=近(?:20|50|100)期)', '\n\n', text)
    parts=re.split(r'\n\s*\n|\n[━─—]{3,}\n',text)
    result=[]
    for part in parts:
        lines=[x for x in part.splitlines() if x.strip() and not re.fullmatch(r'[━─—]+',x.strip())]
        current=[];length=0
        for line in lines:
            # Long historical reports continue in the next panel instead of truncating.
            for start in range(0,len(line),700):
                piece=line[start:start+700]
                if length+len(piece)>900 and current:result.append(current);current=[];length=0
                current.append(piece);length+=len(piece)
        if current:result.append(current)
    return result or [['目前沒有資料']]

def bubble(key,title,groups,items,page,total):
    name,color,subtitle=THEMES[key]
    return {'type':'bubble','size':'mega',
            'header':{'type':'box','layout':'vertical','paddingAll':'20px','spacing':'sm','backgroundColor':INK,
                      'contents':[txt(name,'xs','#AABBD0',True),txt(title,'xl','#FFFFFF',True),
                                  txt(subtitle+ (f' · {page}/{total}' if total>1 else ''),'xs','#CBD5E1')]},
            'body':{'type':'box','layout':'vertical','spacing':'md','paddingAll':'16px','backgroundColor':BG,
                    'contents':[section(g,color) for g in groups]},
            'footer':footer(items,color)}

def build_messages(text,quick_items=None):
    raw=public_text(text);key=theme(raw)
    first=raw.split('\n',1)[0].strip('【】 ')
    title=re.sub(r'^[^\w\u4e00-\u9fff]+','',first)
    title=re.sub(r'\s*V(?:15|2(?:\.\d+)?).*$', '',title).strip()
    if len(title)>32:title=THEMES[key][0]
    groups=sections(raw)
    if groups and groups[0] and groups[0][0]==first and len(groups[0])==1:groups=groups[1:] or [['選一個功能開始。']]
    # A visible native menu replaces the horizontally hidden quick-reply-only menu.
    if raw.startswith('🎲 AI 理性陪跑') and '目前進度' not in raw:
        title='今天想看哪個模式？';key='home'
        groups=[['百家 AI','傳路單 → 核對 → 即時分析'],['539 AI','每日母盤、核心號碼與開獎驗證'],['Bingo AI','近20／50／100期的真實資料統計'],
                [line for line in raw.splitlines() if line.startswith('目前：')]]
    pages=[groups[i:i+3] for i in range(0,len(groups),3)]
    if key=='home' and title=='今天想看哪個模式？':pages=[groups]
    bubbles=[bubble(key,title,g,quick_items,i+1,len(pages)) for i,g in enumerate(pages)]
    messages=[]
    for i in range(0,len(bubbles),4):
        group=bubbles[i:i+4]
        content=group[0] if len(group)==1 else {'type':'carousel','contents':group}
        messages.append({'type':'flex','altText':raw[:400] or title,'contents':content})
    # Oversized content retains the existing text transport rather than losing detail.
    if len(messages)>5 or any(len(json.dumps(m,ensure_ascii=False).encode())>48000 for m in messages):
        messages=[{'type':'text','text':raw[i:i+4800]} for i in range(0,len(raw),4800)][:5]
    if quick_items:
        messages[-1]['quickReply']={'items':[{'type':'action','action':action(a,b)} for a,b in quick_items[:13]]}
    return messages
