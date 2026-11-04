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
