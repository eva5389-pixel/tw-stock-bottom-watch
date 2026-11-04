from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import pandas as pd
import streamlit as st
from data import load_market
from analysis import analyze, report
from futures_ui import render_futures

st.set_page_config(page_title='台股止跌觀察', page_icon=':material/monitoring:', layout='wide')
st.title('台股止跌觀察')
st.caption('先看價格是否守穩，再用市場廣度與籌碼交叉確認。證交所盤後資料｜上市市場')
st.info('這是透明規則的觀察工具，不是預測勝率；不會因融資減少就判定落底。')

@st.cache_data(ttl=300, max_entries=12, show_spinner=False)
def cached_market(day):
    return load_market(day)

today = datetime.now(ZoneInfo('Asia/Taipei')).date()
with st.form('query'):
    selected_text = st.text_input('觀察截止日期（YYYY-MM-DD）', value=today.isoformat())
    st.caption('可查當日已公布的盤後資料，非盤中即時判斷。融資等未公布時會標示資料不足；休市日採最近交易日。首次載入約30–90秒。')
    refresh = st.checkbox('重新向證交所取得資料（不使用五分鐘快取）')
    submit = st.form_submit_button('更新止跌觀察', type='primary')
try:
    selected = datetime.strptime(selected_text, '%Y-%m-%d').date()
    if not today-timedelta(days=365) <= selected <= today:
        raise ValueError('請輸入最近一年內、今天或以前的日期')
except ValueError:
    st.error('請以 YYYY-MM-DD 輸入最近一年內、今天或以前的日期。')
    st.stop()
if submit:
    st.session_state.pop('market_bundle', None)
    try:
        if refresh: cached_market.clear()
        with st.spinner('讀取官方指數、成交金額與最近六個交易日籌碼…'):
            st.session_state.market_bundle = cached_market(selected.isoformat())
    except Exception as exc:
        st.error(f'無法完成更新：{exc}。請稍後重試；不會顯示模擬行情。')
render_futures()
bundle = st.session_state.get('market_bundle')
if not bundle:
    st.write('點選「更新止跌觀察」，即可查看結論、每項依據、走勢圖與下載報告。')
    st.stop()
if bundle['requested'] != selected.isoformat():
    st.warning(f"下方仍為截止 {bundle['requested']} 的結果，請按更新套用新日期。")
try:
    result = analyze(bundle)
except ValueError as exc:
    st.error(str(exc))
    st.stop()
df = result['frame']
last, prev = df.iloc[-1], df.iloc[-2]
if last.date.date() < selected:
    st.warning(f'查詢截止 {selected}，但指數最新僅公布至 {last.date:%Y-%m-%d}；下方是該交易日結果，不能視為查詢當日已確認止跌。')
elif result['available'] < 6:
    st.warning('當日價格已取得，但部分籌碼尚未取得／公布；目前僅為不完整資料的觀察結果。')
with st.container(border=True):
    st.subheader(result['label'])
    st.write(f"資料截至 **{last.date:%Y-%m-%d}**｜擷取時間：{bundle['fetched_at']}")
    st.write(f"6 項條件中 **{result['count']} 項支持**，**{6-result['available']} 項資料不足**。此數量不是機率。")
    with st.container(horizontal=True):
        st.metric('加權指數收盤', f'{last.close:,.2f}', f'{(last.close/prev.close-1)*100:+.2f}%', delta_color='off', border=True)
        st.metric('前20交易日低點', f"{result['support']:,.2f}", border=True)
        st.metric('當日融資變動（億元）', '未取得' if pd.isna(last.margin_change) else f'{last.margin_change:+,.2f}', border=True)
        st.metric('當日外資買賣超（億元）', '未取得' if pd.isna(last.foreign_net) else f'{last.foreign_net:+,.2f}', border=True)
if result['invalid']:
    st.warning('指數月份資料有缺漏，或距查詢截止日超過7天。下列僅供檢查資料，不形成止跌結論。')
from putcall import render as render_putcall
render_putcall(bundle, result)
st.subheader('逐項判斷依據')
st.dataframe(pd.DataFrame(result['signals']), hide_index=True, width='stretch')
st.write('**較高低點後突破：** '+('成立' if result['pattern'] else '尚未成立'))
if result['neckline'] is not None:
    st.caption(f"最近兩個確認波段低點間的高點：{result['neckline']:,.2f}；第二低點：{result['pivot_support']:,.2f}。線位不是保證支撐。")
st.subheader('價格與成交金額')
chart_data = df[['date','close','MA5','MA20']].melt('date', var_name='series', value_name='value').dropna()
chart_data['series'] = chart_data['series'].map({'close':'加權收盤','MA5':'5日均線','MA20':'20日均線'})
st.vega_lite_chart(chart_data, {
    'mark': 'line', 'height': 330,
    'encoding': {
        'x': {'field':'date','type':'temporal','title':'日期'},
        'y': {'field':'value','type':'quantitative','title':'指數','scale':{'zero':False}},
        'color': {'field':'series','type':'nominal','title':'指標'},
        'tooltip': [{'field':'date','type':'temporal','title':'日期'},{'field':'series','type':'nominal','title':'指標'},{'field':'value','type':'quantitative','title':'點數','format':',.2f'}]
    }
})
turnover_data = df[['date','turnover']].copy()
turnover_data['turnover'] /= 1e8
st.vega_lite_chart(turnover_data, {
    'mark': 'bar', 'height': 220,
    'encoding': {
        'x': {'field':'date','type':'temporal','title':'日期'},
        'y': {'field':'turnover','type':'quantitative','title':'成交金額（億元）'},
        'tooltip': [{'field':'date','type':'temporal','title':'日期'},{'field':'turnover','type':'quantitative','title':'億元','format':',.2f'}]
    }
})
st.subheader('最近六個交易日籌碼')
recent = df.tail(6).copy()
recent['上漲比率'] = recent.advances / (recent.advances+recent.declines+recent.unchanged)
st.dataframe(recent[['date','advances','declines','上漲比率','margin','margin_change','cash_repayment','foreign_net']].rename(columns={'date':'日期','advances':'上漲家數','declines':'下跌家數','margin':'融資餘額（億）','margin_change':'融資變動（億）','cash_repayment':'現金償還（億）','foreign_net':'外資買賣超（億）'}), hide_index=True, column_config={'上漲比率':st.column_config.NumberColumn(format='percent')})
st.caption('融資變動採各日公布的今日餘額減前日餘額；前日值可能經更正，因此不一定等於相鄰列餘額相減。現金償還是融資減少的一部分。')
with st.expander('規則、限制與判斷失效條件'):
    st.markdown('''- 當日最低跌破此前20日低點：優先顯示「仍創新低」，其他項目不能抵銷。
- 近三日守低：最近三日最低均不低於此前20日最低；不等於已完成回測。
- 波段低點須左右各有兩根已完成日K確認；取最近40日的最近兩個低點，至少間隔3日。
- 較高低點後突破：第一低點距此前最多20日高點至少回落3%；第二低點較高，之後未跌破第二低點，最新收盤突破兩低點之間最高價。
- 「止跌訊號增加」須上述型態成立、六項資料齊全且至少四項支持。門檻為人工設定，尚未回測，無勝率含義。
- 不符合上述條件，但近三日守低且站上5日線，僅列反彈／築底觀察。
- 缺值不填零、不沿用舊日資料。當日最低再破前低，必須重新評估；價格站回均線可能仍是假突破。
- 本版不含櫃買、個股創新低家數或期貨法人部位，不能據此代表全部台股。
- 未取得全市場帳戶維持率與成本分布，不推算集體融資斷頭價，也不預測底部或提供自動交易。''')
with st.expander('資料來源與擷取狀態'):
    st.dataframe(pd.DataFrame(bundle['audit']), hide_index=True, column_config={'來源':st.column_config.LinkColumn()})
    for error in bundle['errors']: st.warning(error)
    st.caption('現貨資料來自證交所，選擇權P/C來自期交所；資料可能延遲、更正或暫時限制存取。來源失敗時請稍後重試。')
st.download_button('下載觀察報告（Markdown）', report(bundle,result), file_name=f'taiwan-bottom-watch-{last.date:%Y%m%d}.md', mime='text/markdown')
st.download_button('下載行情與籌碼（CSV）', df.to_csv(index=False).encode('utf-8-sig'), file_name=f'taiwan-bottom-watch-{last.date:%Y%m%d}.csv', mime='text/csv')
