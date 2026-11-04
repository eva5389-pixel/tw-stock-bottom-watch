import pandas as pd
import streamlit as st
from futures import load_reference, thresholds, MARGIN_URL, QUOTE_URL

@st.cache_data(ttl=300, show_spinner=False)
def reference():
    return load_reference()

def render_futures():
    with st.expander('大台多單：追繳與強制平倉點位試算', expanded=True):
        st.caption('每口每點新臺幣200元。僅適用現金權益、單一大台多單，無其他期貨、選擇權或加收保證金。這是個別帳戶壓力試算，不是全市場斷頭價。')
        if st.button('載入最新官方保證金與近月日盤收盤價'):
            try:
                reference.clear()
                with st.spinner('取得期交所參考資料…'):
                    ref = reference()
                st.session_state.tx_reference = ref
                for key in ['price','original','maintenance']:
                    st.session_state['tx_'+key] = ref[key]
            except Exception as exc:
                st.error(f'官方參考資料取得失敗：{exc}。可依期貨商帳戶手動輸入。')
        ref = st.session_state.get('tx_reference')
        if ref:
            st.caption(f"參考合約 TX {ref['month']}｜一般交易時段 {ref['date']} 收盤；非即時報價。擷取：{ref['fetched']}。保證金為目前公告值，不是歷史回溯值。")
        st.markdown(f'[期交所保證金公告]({MARGIN_URL}) · [期貨日報資料]({QUOTE_URL})')
        with st.form('tx_calculator'):
            price = st.number_input('目前大台期貨價格（點）', min_value=0.0, value=0.0, key='tx_price')
            contracts = st.number_input('持有大台多單口數', min_value=1, value=1, step=1)
            original = st.number_input('每口原始保證金（元，依期貨商要求）', min_value=0.0, value=0.0, key='tx_original')
            maintenance = st.number_input('每口維持保證金（元）', min_value=0.0, value=0.0, key='tx_maintenance')
            hypothetical = st.checkbox('假設目前帳戶權益剛好等於原始保證金總額', value=True)
            equity_input = st.number_input('目前帳戶權益（元，含浮動損益；取消上方假設才使用）', value=0.0)
            ratio = st.number_input('期貨商約定強平風險比率（%）', min_value=25.0, max_value=100.0, value=25.0)
            calculate = st.form_submit_button('計算還可下跌幾點／幾％')
        st.warning('低於維持保證金可能收到追繳；未依期限補足，也可能在到達風險比率門檻前被平倉。25%只是可調整的示例，須依期貨商契約；跳空與滑價會讓實際成交更差。')
        st.caption('計算：門檻點位＝目前期貨價－（目前權益－門檻權益）÷（口數×200）。不等同加權指數點位；當沖減收、跨商品及選擇權組合不適用。')
        st.markdown('[期交所交易風險說明](https://www.taifex.com.tw/file/taifex/event/cht/investmentRisk/index.html)')
        if calculate:
            try:
                equity = contracts*original if hypothetical else equity_input
                rows = thresholds(price, contracts, equity, original, maintenance, ratio)
                st.session_state.tx_result = (f"{'假設情境' if hypothetical else '自填帳戶情境'}：參考價 {price:,.0f} 點、{contracts} 口多單、目前權益 {equity:,.0f} 元、強平比率 {ratio:g}%。", rows)
            except ValueError as exc:
                st.session_state.pop('tx_result', None)
                st.error(str(exc))
        if 'tx_result' in st.session_state:
            label, rows = st.session_state.tx_result
            st.write('**上次按下計算的結果**｜'+label)
            st.dataframe(pd.DataFrame(rows), hide_index=True)
            st.caption('表中為理論門檻；觸發通常為低於門檻，實際依整數跳動點與期貨商規則處理。更改欄位後請重新計算。')
