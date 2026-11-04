"""Explainable observation rules, not a fitted model or probability forecast."""
import pandas as pd


def analyze(bundle):
    df = bundle['data'].copy().sort_values('date').reset_index(drop=True)
    if df.date.duplicated().any(): raise ValueError('行情日期重複')
    if len(df) < 25: raise ValueError('至少需要 25 個交易日，暫不判斷。')
    required = df[['open','high','low','close']]
    if required.isna().any().any() or (required <= 0).any().any():
        raise ValueError('指數資料不完整或無效')
    if ((df.high < df[['open','close','low']].max(axis=1)) | (df.low > df[['open','close']].min(axis=1))).any():
        raise ValueError('指數高低價核對不符')
    df['MA5'] = df.close.rolling(5).mean()
    df['MA20'] = df.close.rolling(20).mean()
    last, prev = df.iloc[-1], df.iloc[-2]
    support = float(df.low.iloc[-21:-1].min())
    new_low = bool(last.low < support)
    rows = []
    def signal(name, ok, detail):
        rows.append({'項目':name,'狀態':'資料不足' if ok is None else ('支持' if ok else '未支持'),'依據':detail})
    held = bool((df.low.iloc[-3:] >= df.low.iloc[-23:-3].min()).all())
    signal('近三日守住前低', held and not new_low, f'最近三日最低 {df.low.iloc[-3:].min():,.2f}；此前20日最低 {df.low.iloc[-23:-3].min():,.2f}。')
    ma_ok = bool(last.close > last.MA5 and last.close > last.MA20 and last.MA5 > prev.MA5)
    signal('均線修復', ma_ok, f'收盤 {last.close:,.2f}；5日均線 {last.MA5:,.2f}（須上彎）；20日均線 {last.MA20:,.2f}。')
    avg_turnover = df.turnover.iloc[-21:-1].mean() if df.turnover.iloc[-21:-1].notna().all() else float('nan')
    if pd.notna(last.turnover) and pd.notna(avg_turnover) and avg_turnover > 0:
        ratio = last.turnover/avg_turnover
        signal('上漲有成交金額配合', bool(last.close > prev.close and ratio >= 1.1), f'當日漲跌 {(last.close/prev.close-1)*100:+.2f}%；成交金額為此前20日均值 {ratio:.2f} 倍（門檻1.10）。此項不衡量回測量縮。')
    else: signal('上漲有成交金額配合', None, '需要當日及此前20個交易日成交金額。')
    b = df.tail(3)[['advances','declines','unchanged']]
    if b.notna().all().all() and (b.sum(axis=1)>0).all():
        ratios = b.advances/b.sum(axis=1)
        signal('多數股票參與', bool((ratios > .5).sum() >= 2), f'最近3日有 {(ratios>.5).sum()} 日，上漲家數占漲／跌／持平股票總數超過50%；當日 {ratios.iloc[-1]:.1%}。不含未成交、無比價。')
    else: signal('多數股票參與', None, '需要連續3個交易日的股票漲跌家數，不沿用舊日期。')
    changes = df.margin_change.tail(5)
    if changes.notna().all():
        delta = changes.sum()
        signal('融資減少且價格守穩', bool(delta < 0 and held and not new_low), f'近5日融資淨變動 {delta:+,.2f} 億元；需同時守住前低。減少含主動賣出及現金償還，不能等同斷頭。')
    else: signal('融資減少且價格守穩', None, '需要連續5日融資變動，缺值不視為零。')
    flow = df.foreign_net.tail(6)
    if flow.notna().all():
        recent, older = flow.iloc[-3:].sum(), flow.iloc[:3].sum()
        signal('外資現貨賣壓改善', bool(recent >= 0 or (older < 0 and recent > older)), f'近3日合計 {recent:+,.2f} 億元；前3日 {older:+,.2f} 億元。近3日買超或負值縮小為支持；不等於匯入。')
    else: signal('外資現貨賣壓改善', None, '需要連續6日上市外資現貨買賣超。')
    # Confirmed pivot lows: two observed bars on either side, no future bar access.
    pivots = [i for i in range(max(2,len(df)-40),len(df)-2)
              if df.low.iloc[i] < df.low.iloc[i-2:i].min() and df.low.iloc[i] <= df.low.iloc[i+1:i+3].min()]
    pattern, neckline, pivot_support = False, None, None
    if len(pivots) >= 2:
        a, bidx = pivots[-2:]
        if bidx-a >= 3:
            neckline = float(df.high.iloc[a+1:bidx].max())
            pivot_support = float(df.low.iloc[bidx])
            prior_peak = df.high.iloc[max(0,a-20):a].max()
            pattern = bool(df.low.iloc[bidx] > df.low.iloc[a] and
                           df.low.iloc[bidx+1:].min() >= pivot_support and
                           last.close > neckline and df.low.iloc[a]/prior_peak <= .97)
    count = sum(r['狀態']=='支持' for r in rows)
    available = sum(r['狀態']!='資料不足' for r in rows)
    stale = (pd.Timestamp(bundle['requested'])-last.date).days > 7
    invalid = stale or not bundle.get('price_complete', True)
    if invalid: label = '資料不足，暫不判斷'
    elif new_low: label = '仍創新低，止跌未確認'
    elif pattern and count >= 4 and available == 6: label = '止跌訊號增加，仍需持續確認'
    elif held and last.close > last.MA5: label = '反彈／築底觀察，尚未確認'
    else: label = '止跌未確認'
    return {'frame':df,'signals':rows,'label':label,'support':support,'neckline':neckline,
            'pivot_support':pivot_support,'pattern':pattern,'count':count,'available':available,
            'stale':stale,'invalid':invalid,'new_low':new_low}


def report(bundle, result):
    lines = ['# 台股止跌觀察',f"資料截至：{result['frame'].date.iloc[-1]:%Y-%m-%d}",
             f"擷取時間（台北）：{bundle['fetched_at']}",f"判斷：{result['label']}",
             f"觀察條件：{result['count']}/6 支持；{6-result['available']} 項資料不足。不是勝率。",
             f"前20交易日低點：{result['support']:,.2f}",
             f"較高低點後突破：{'成立' if result['pattern'] else '未成立'}",'']
    for row in result['signals']: lines.append(f"- {row['項目']}：{row['狀態']}。{row['依據']}")
    from putcall import assessment, COLUMNS
    lines += ['', '## 臺指選擇權Put／Call交叉判讀', assessment(bundle.get('putcall', pd.DataFrame(columns=COLUMNS)), result), 'P/C為賣權÷買權×100%；無法區分買賣方動機，結算轉倉會影響比率。本項不計入六項分數，也不是單獨止跌訊號。']
    lines += ['', '僅分析上市加權指數與上市股票；不代表上櫃或個股。規則尚未回測，非買賣建議或落底保證。',
              '融資餘額無法推算全市場整戶維持率或集體斷頭價；未以期貨保證金替代融資資料。',
              '盤後日資料；無即時報價。官方可能更正歷史資料，重新查詢結果可能變動。', '', '## 資料來源']
    for a in bundle['audit']: lines.append(f"- {a['資料']} {a['查詢日期']}：{a['狀態']}；{a['來源']}")
    lines.extend(bundle['errors'])
    return '\n'.join(lines)
