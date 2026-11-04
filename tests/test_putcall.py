import unittest
import pandas as pd
from putcall import parse, assessment

class PutCallTests(unittest.TestCase):
    def row(self,date):
        return dict(Date=date,PutVolume='80',CallVolume='100',PutOI='50',CallOI='100',**{'PutCallVolumeRatio%':'80','PutCallOIRatio%':'50'})
    def test_cutoff_and_units(self):
        df=parse([self.row('20261103'),self.row('20261104')],'2026-11-03')
        self.assertEqual(len(df),1)
        self.assertEqual(df.iloc[0]['成交量P/C（%）'],80)
    def test_reconciliation(self):
        r=self.row('20261103');r['PutCallOIRatio%']='0.5'
        with self.assertRaises(ValueError): parse([r],'2026-11-03')
    def test_alignment_and_no_override(self):
        result={'frame':pd.DataFrame({'date':pd.to_datetime(['2026-10-30','2026-11-02','2026-11-03'])}),'invalid':False,'new_low':True,'pattern':False}
        df=parse([self.row(d) for d in ['20261030','20261102','20261103']],'2026-11-03')
        self.assertIn('不能抵銷',assessment(df,result))
        self.assertIn('資料不足',assessment(df.iloc[:-1],result))

    def test_official_web_table(self):
        from putcall import parse_page
        html='<table><tr><td>2026/11/4</td><td>435,537</td><td>512,374</td><td>85.00</td><td>49,447</td><td>100,151</td><td>49.37</td></tr></table>'
        df=parse_page(html,'2026-11-04')
        self.assertEqual(df.iloc[0]['未平倉P/C（%）'],49.37)
        self.assertTrue(parse_page(html,'2026-11-03').empty)
