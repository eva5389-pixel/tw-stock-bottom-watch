"""Official aggregate TXO ratios: contextual evidence, not directional positions."""
import math
import pandas as pd
import requests

PAGE = 'https://www.taifex.com.tw/cht/3/pcRatio'
API = 'https://openapi.taifex.com.tw/v1/PutCallRatio'
COLUMNS = ['date','賣權成交量','買權成交量','成交量P/C（%）','賣權未平倉量','買權未平倉量','未平倉P/C（%）']

def parse(payload, asof):
    rows=[]
    for r in payload:
        date=pd.to_datetime(r['Date'],format='%Y%m%d')
        if date > pd.Timestamp(asof): continue
        nums=[float(str(r[k]).replace(',','')) for k in ['PutVolume','CallVolume','PutCallVolumeRatio%','PutOI','CallOI','PutCallOIRatio%']]
        if not all(math.isfinite(v) and v>=0 for v in nums) or nums[1]<=0 or nums[4]<=0:
            raise ValueError('P/C數值或分母無效')
        if abs(nums[0]/nums[1]*100-nums[2])>.02 or abs(nums[3]/nums[4]*100-nums[5])>.02:
            raise ValueError('P/C比率與口數核對不符')
        rows.append([date]+nums)
    df=pd.DataFrame(rows,columns=COLUMNS).sort_values('date').reset_index(drop=True)
    if df.date.duplicated().any(): raise ValueError('P/C日期重複')
    return df

def parse_page(html, asof):
    import re
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'html.parser')
    payload = []
    for tr in soup.select('tr'):
        cells = [c.get_text(' ', strip=True) for c in tr.find_all('td', recursive=False)]
        if len(cells) != 7 or not re.fullmatch(r'\d{4}/\d{1,2}/\d{1,2}', cells[0]):
            continue
        date = pd.to_datetime(cells[0]).strftime('%Y%m%d')
        keys = ['PutVolume','CallVolume','PutCallVolumeRatio%','PutOI','CallOI','PutCallOIRatio%']
        payload.append(dict(Date=date, **dict(zip(keys,cells[1:]))))
    if not payload: raise ValueError('官方網頁未取得P/C資料表')
    return parse(payload, asof)

def load(asof):
    frames, notes = [], []
    for url, parser in [(API, lambda r: parse(r.json(),asof)), (PAGE, lambda r: parse_page(r.text,asof))]:
        try:
            r=requests.get(url,timeout=(8,20)); r.raise_for_status()
            frame=parser(r)
            if not frame.empty:
                frame['來源']=url
                frames.append(frame)
        except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
            notes.append(f'{url}：{type(exc).__name__}')
    if not frames: raise ValueError('官方API與網頁均無可用資料：'+'；'.join(notes))
    # The official web table wins for overlapping dates; both use identical reconciliation.
    merged=pd.concat(frames).drop_duplicates('date',keep='last').sort_values('date').reset_index(drop=True)
    merged.attrs['warnings']=notes
    return merged

def assessment(frame, result):
    if frame.empty: return '資料不足：官方API回傳範圍內沒有截止日以前的P/C資料。'
    dates=result['frame'].date.tail(3).tolist()
    aligned=frame[COLUMNS].set_index('date').reindex(dates)
    if aligned.isna().any().any():
        return f'資料不足：最新P/C為 {frame.date.iloc[-1]:%Y-%m-%d}；與現貨最近三個交易日未完整對齊，不納入當日交叉判讀。'
    vol=aligned['成交量P/C（%）']; oi=aligned['未平倉P/C（%）']
    trend='上升' if oi.iloc[-1]>oi.iloc[0] else ('下降' if oi.iloc[-1]<oi.iloc[0] else '持平')
    detail=f'近三個對齊交易日，未平倉P/C{trend} {oi.iloc[-1]-oi.iloc[0]:+.2f} 個百分點；最新成交量P/C {vol.iloc[-1]:.2f}%，未平倉P/C {oi.iloc[-1]:.2f}%。'
    if result['invalid']: context='現貨資料不足，暫不判斷止跌。'
    elif result['new_low']: context='現貨仍創前20日新低，P/C不能抵銷破底訊號，止跌仍未確認。'
    elif result['pattern']: context='現貨已有較高低點後突破型態；P/C僅補充部位結構，不能單獨確認多頭。'
    else: context='現貨尚未完成較高低點後突破；P/C變化不足以確認止跌。'
    return detail+context

def render(bundle,result):
    import streamlit as st
    st.subheader('臺指選擇權 Put／Call 比：交叉判讀')
    frame=bundle.get('putcall',pd.DataFrame(columns=COLUMNS))
    text=assessment(frame,result)
    st.write(text)
    st.caption('P/C＝賣權÷買權×100%；100%等於1倍。成交量反映交易活動，未平倉量反映尚未了結口數。每口同時有買方與賣方，無法從總量分辨買進避險或賣出收權利金；結算與轉倉也會改變比率。')
    st.caption('此項作為補充判讀，不加進原六項支持分數；不使用「高於100%就看多／看空」的固定門檻。')
    if not frame.empty:
        st.dataframe(frame.tail(10).sort_values('date',ascending=False).rename(columns={'date':'日期'}),hide_index=True)
        chart=frame.melt('date',value_vars=['成交量P/C（%）','未平倉P/C（%）'],var_name='比率',value_name='數值')
        st.vega_lite_chart(chart,{'mark':'line','height':250,'encoding':{'x':{'field':'date','type':'temporal','title':'日期'},'y':{'field':'數值','type':'quantitative','title':'P/C（%）'},'color':{'field':'比率','type':'nominal'},'tooltip':[{'field':'date','type':'temporal'},{'field':'比率','type':'nominal'},{'field':'數值','type':'quantitative'}]}})
        st.download_button('下載Put／Call資料（CSV）',frame.to_csv(index=False).encode('utf-8-sig'),file_name='put-call-ratio.csv',mime='text/csv')
    st.markdown(f'[期交所Put／Call比]({PAGE}) · [官方API]({API})')
