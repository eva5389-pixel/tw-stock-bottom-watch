"""TWSE public end-of-day reports; no credentials, synthetic or substituted data."""
from datetime import date, datetime
from zoneinfo import ZoneInfo
import re
import time
import pandas as pd
import requests

BASE = 'https://www.twse.com.tw'
SOURCES = {
    'price': '/indicesReport/MI_5MINS_HIST',
    'turnover': '/exchangeReport/FMTQIK',
    'breadth': '/exchangeReport/MI_INDEX',
    'margin': '/exchangeReport/MI_MARGN',
    'foreign': '/rwd/zh/fund/BFI82U',
}
LABELS = {'price':'加權指數', 'turnover':'市場成交金額', 'breadth':'上市股票漲跌家數', 'margin':'上市融資', 'foreign':'上市外資買賣超'}


def num(value):
    n = float(str(value).replace(',', '').strip())
    if not pd.notna(n) or abs(n) == float('inf'):
        raise ValueError('非有限數值')
    return n


def roc_date(value):
    y, m, d = map(int, value.split('/'))
    return pd.Timestamp(date(y + 1911 if y < 1911 else y, m, d))


def check_day(payload, day):
    if payload.get('stat') != 'OK' or payload.get('date') != day:
        raise ValueError('資料日期不符或尚未公布')


def table(payload, fields):
    candidates = [payload] + payload.get('tables', [])
    for item in candidates:
        if set(fields).issubset(item.get('fields', [])) and item.get('data'):
            return pd.DataFrame(item['data'], columns=item['fields'])
    raise ValueError('找不到必要資料欄位')


def parse_month(payload, kind):
    if payload.get('stat') != 'OK':
        raise ValueError('月資料尚未公布或取得失敗')
    mapping = {'開盤指數':'open', '最高指數':'high', '最低指數':'low', '收盤指數':'close'} if kind == 'price' else {'成交金額':'turnover'}
    frame = table(payload, ['日期', *mapping])
    result = pd.DataFrame({'date':frame['日期'].map(roc_date)})
    for source, target in mapping.items():
        result[target] = frame[source].map(num)
    return result


def parse_day(payload, kind, day):
    check_day(payload, day)
    if kind == 'breadth':
        df = table(payload, ['類型', '股票']).set_index('類型')
        # Use 股票, never 整體市場 (the latter includes warrants).
        values = {}
        for label, key in [('上漲(漲停)', 'advances'), ('下跌(跌停)', 'declines'), ('持平', 'unchanged')]:
            raw = str(df.loc[label, '股票']).replace(',', '')
            if not re.fullmatch(r'\d+(\(\d+\))?', raw):
                raise ValueError('漲跌家數格式變更')
            values[key] = int(raw.split('(')[0])
        return values
    if kind == 'margin':
        df = table(payload, ['項目','前日餘額','今日餘額','買進','賣出','現金(券)償還']).set_index('項目')
        row = df.loc['融資金額(仟元)']
        v = {k:num(row[k]) for k in ['前日餘額','今日餘額','買進','賣出','現金(券)償還']}
        if abs(v['前日餘額']+v['買進']-v['賣出']-v['現金(券)償還']-v['今日餘額']) > 2:
            raise ValueError('融資餘額核對失敗')
        return {'margin':v['今日餘額']/100000, 'margin_change':(v['今日餘額']-v['前日餘額'])/100000, 'cash_repayment':v['現金(券)償還']/100000}
    df = table(payload, ['單位名稱','買進金額','賣出金額','買賣差額']).set_index('單位名稱')
    row = df.loc['外資及陸資(不含外資自營商)']
    buy, sell, net = [num(row[k]) for k in ['買進金額','賣出金額','買賣差額']]
    if abs(buy-sell-net) > 1:
        raise ValueError('外資買賣金額核對失敗')
    return {'foreign_net':net/100000000}


def load_market(asof):
    """Four calendar months plus six recent trading dates. Every request is audited."""
    asof = pd.Timestamp(asof).normalize()
    audit, errors, prices, turnovers = [], [], [], []
    with requests.Session() as session:
        session.headers.update({'User-Agent':'TaiwanBottomWatch/1.0 (public end-of-day research)'})
        def request(kind, day, monthly=False):
            params = {'response':'json'}
            params.update({'dayDate':day, 'type':'day'} if kind == 'foreign' else {'date':day})
            if kind == 'breadth': params['type'] = 'MS'
            if kind == 'margin': params['selectType'] = 'MS'
            url = BASE + SOURCES[kind]
            record = {'資料':LABELS[kind], '查詢日期':day, '來源':url, '狀態':'成功', '回傳日期':''}
            try:
                r = session.get(url, params=params, timeout=(8, 18))
                r.raise_for_status()
                payload = r.json()
                record['來源'] = r.url
                record['回傳日期'] = payload.get('date','')
                if monthly and str(payload.get('date', ''))[:6] != day[:6]:
                    raise ValueError('回傳月份與查詢月份不符')
                parsed = parse_month(payload, kind) if monthly else parse_day(payload, kind, day)
                return parsed
            except (requests.RequestException, ValueError, KeyError, TypeError, IndexError) as exc:
                record['狀態'] = '未取得／格式不符'
                errors.append(f'{LABELS[kind]} {day}：{type(exc).__name__}，未納入判斷。')
                return None
            finally:
                audit.append(record)
                time.sleep(0.15)
        for offset in range(3, -1, -1):
            month = (asof.replace(day=1) - pd.DateOffset(months=offset)).strftime('%Y%m%d')
            for kind, frames in [('price', prices), ('turnover', turnovers)]:
                frame = request(kind, month, monthly=True)
                if frame is not None: frames.append(frame)
        if not prices:
            raise ValueError('無法取得證交所指數資料。請稍後重試；系統不會以模擬資料替代。')
        df = pd.concat(prices).drop_duplicates('date').sort_values('date')
        df = df[df.date <= asof].reset_index(drop=True)
        if df.empty: raise ValueError('選定日期之前沒有可用行情。')
        if turnovers:
            vol = pd.concat(turnovers).drop_duplicates('date')
            df = df.merge(vol, on='date', how='left')
        else: df['turnover'] = float('nan')
        for col in ['advances','declines','unchanged','margin','margin_change','cash_repayment','foreign_net']:
            df[col] = float('nan')
        for idx in df.tail(6).index:
            day = df.loc[idx,'date'].strftime('%Y%m%d')
            for kind in ['breadth','margin','foreign']:
                values = request(kind, day)
                if values:
                    for key, value in values.items(): df.loc[idx,key] = value
    from putcall import load as load_putcall, API
    pc = pd.DataFrame()
    record = {'資料':'臺指選擇權Put/Call比','查詢日期':str(asof.date()),'來源':API,'狀態':'成功','回傳日期':''}
    try:
        pc = load_putcall(asof)
        if pc.empty: raise ValueError('截止日前無資料')
        record['回傳日期'] = str(pc.date.iloc[-1].date())
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        record['狀態'] = '未取得／格式不符'
        errors.append(f'Put/Call比：{type(exc).__name__}，未納入判讀。')
    audit.append(record)
    return {'data':df, 'putcall':pc, 'audit':audit, 'errors':errors, 'requested':str(asof.date()),
            'fetched_at':datetime.now(ZoneInfo('Asia/Taipei')).isoformat(timespec='seconds'),
            'price_complete':not any(x['資料']=='加權指數' and x['狀態']!='成功' for x in audit)}
