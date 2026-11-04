import unittest
from pathlib import Path
import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest
from analysis import analyze, report
from data import parse_day, parse_month


def bundle():
    closes = np.array([130-i*.7 for i in range(25)]+[111,108,100,104,108,112,110,107,103,106,110,114,115,116,117],dtype=float)
    df = pd.DataFrame({'date':pd.bdate_range(end='2026-11-03',periods=len(closes)), 'open':closes,'high':closes+1,'low':closes-1,'close':closes,'turnover':100.,'advances':700.,'declines':300.,'unchanged':20.,'margin':1000.,'margin_change':-2.,'cash_repayment':1.,'foreign_net':5.})
    df.loc[df.index[-1],'turnover']=150.
    return {'data':df,'requested':'2026-11-03','fetched_at':'test','errors':[],'audit':[], 'price_complete':True}

class AnalysisTests(unittest.TestCase):
    def test_higher_low_breakout(self):
        r=analyze(bundle()); self.assertTrue(r['pattern']); self.assertIn('訊號增加',r['label'])
    def test_new_low_overrides_positive_flows(self):
        b=bundle(); b['data'].loc[b['data'].index[-1],['open','low','close']]=90
        r=analyze(b); self.assertTrue(r['new_low']); self.assertIn('仍創新低',r['label'])
    def test_missing_is_not_zero(self):
        b=bundle(); b['data'].loc[b['data'].index[-2],'foreign_net']=float('nan')
        r=analyze(b); self.assertEqual(r['available'],5); self.assertNotIn('訊號增加',r['label'])
    def test_stale_and_month_gap(self):
        b=bundle(); b['requested']='2026-11-20'; self.assertTrue(analyze(b)['invalid'])
        b=bundle(); b['price_complete']=False; self.assertIn('資料不足',analyze(b)['label'])
    def test_break_of_second_low_invalidates_pattern(self):
        b=bundle(); b['data'].loc[b['data'].index[-1],'low']=101
        self.assertFalse(analyze(b)['pattern'])
    def test_no_lookahead_on_truncated_data(self):
        b=bundle(); b['data']=b['data'].iloc[:34]; b['requested']=str(b['data'].date.iloc[-1].date())
        self.assertFalse(analyze(b)['pattern'])
    def test_dates_sorted_and_report(self):
        b=bundle(); b['data']=b['data'].iloc[::-1]; r=analyze(b)
        self.assertIn('不是勝率',report(b,r))
    def test_ui_without_sending_or_network(self):
        at=AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'streamlit_app.py')).run()
        self.assertEqual(len(at.exception),0)
        at.session_state['market_bundle']=bundle()
        at.run()
        self.assertEqual(len(at.exception),0)
        self.assertGreater(len(at.dataframe),1)

class ParserTests(unittest.TestCase):
    def test_breadth_excludes_warrants(self):
        p={'stat':'OK','date':'20261103','tables':[{'fields':['類型','整體市場','股票'],'data':[['上漲(漲停)','9999(1)','58(2)'],['下跌(跌停)','10000(3)','1000(33)'],['持平','341','22']]}]}
        self.assertEqual(parse_day(p,'breadth','20261103')['advances'],58)
        with self.assertRaises(ValueError): parse_day(p,'breadth','20261102')
    def test_margin_units_and_reconciliation(self):
        p={'stat':'OK','date':'20261103','tables':[{'fields':['項目','買進','賣出','現金(券)償還','前日餘額','今日餘額'],'data':[['融資金額(仟元)','100000','200000','50000','1000000','850000']]}]}
        r=parse_day(p,'margin','20261103'); self.assertEqual(r['margin'],8.5);self.assertEqual(r['margin_change'],-1.5)
        p['tables'][0]['data'][0][-1]='1'
        with self.assertRaises(ValueError):parse_day(p,'margin','20261103')
    def test_roc_date(self):
        p={'stat':'OK','fields':['日期','開盤指數','最高指數','最低指數','收盤指數'],'data':[['115/10/01','100','102','99','101']]}
        self.assertEqual(str(parse_month(p,'price').date.iloc[0].date()),'2026-10-01')

if __name__=='__main__':unittest.main()
