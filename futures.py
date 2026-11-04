"""TX long-only, cash-equity scenario calculator; not a market forecast."""
import math
import re
from datetime import datetime
from zoneinfo import ZoneInfo
import requests
from bs4 import BeautifulSoup

MARGIN_URL = 'https://www.taifex.com.tw/cht/5/indexMarging'
QUOTE_URL = 'https://openapi.taifex.com.tw/v1/DailyMarketReportFut'

def thresholds(price, contracts, equity, original, maintenance, ratio):
    values = [price, contracts, equity, original, maintenance, ratio]
    if not all(math.isfinite(float(v)) for v in values):
        raise ValueError('輸入必須為有限數值')
    if price <= 0 or contracts < 1 or int(contracts) != contracts or not 0 < maintenance <= original or not 25 <= ratio <= 100:
        raise ValueError('請檢查價格、口數、保證金與風險比率')
    rows = []
    for name, target in [('追繳門檻（維持保證金）', contracts*maintenance), ('風險比率強平門檻', contracts*original*ratio/100)]:
        distance = (equity-target)/(200*contracts)
        level = price-distance
        status = '已達／低於門檻' if distance <= 0 else ('正價格範圍內未達' if level <= 0 else '尚未觸及')
        rows.append({'門檻':name, '權益門檻（元）':target, '估算期貨點位':level if 0 < level <= price else None, '還可下跌點數':max(0,distance) if level > 0 else None, '距門檻跌幅（%）':max(0,distance)/price*100 if level > 0 else None, '狀態':status})
    return rows

def load_reference():
    response = requests.get(MARGIN_URL, timeout=20)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')
    margin = None
    for tr in soup.select('tr'):
        cells = [c.get_text(' ', strip=True) for c in tr.find_all(['td','th'])]
        if cells and cells[0] == '臺股期貨' and len(cells) == 4:
            nums = [float(c.replace(',','')) for c in cells[1:]]
            margin = {'original':nums[2], 'maintenance':nums[1]}
    if not margin or not 0 < margin['maintenance'] <= margin['original']:
        raise ValueError('無法辨識官方大台保證金表')
    response = requests.get(QUOTE_URL, timeout=20)
    response.raise_for_status()
    rows = [r for r in response.json() if r.get('Contract') == 'TX' and r.get('TradingSession') == '一般' and re.fullmatch(r'\d{6}', r.get('ContractMonth(Week)',''))]
    latest = max(r['Date'] for r in rows)
    row = min((r for r in rows if r['Date']==latest), key=lambda r:r['ContractMonth(Week)'])
    price = float(row['Last'].replace(',',''))
    if not math.isfinite(price) or price <= 0: raise ValueError('期貨價格無效')
    return dict(**margin, price=price, date=latest, month=row['ContractMonth(Week)'], fetched=datetime.now(ZoneInfo('Asia/Taipei')).isoformat(timespec='seconds'))
