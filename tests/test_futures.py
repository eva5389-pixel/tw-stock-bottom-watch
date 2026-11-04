import unittest
from pathlib import Path
from futures import thresholds
from streamlit.testing.v1 import AppTest

class FuturesTests(unittest.TestCase):
    def test_original_equity(self):
        rows = thresholds(43376, 1, 701000, 701000, 538000, 25)
        self.assertEqual(rows[0]['還可下跌點數'], 815)
        self.assertEqual(rows[0]['估算期貨點位'], 42561)
        self.assertEqual(rows[1]['還可下跌點數'], 2628.75)
    def test_size_scaling(self):
        a = thresholds(40000, 1, 800000, 701000, 538000, 25)
        b = thresholds(40000, 2, 1600000, 701000, 538000, 25)
        self.assertEqual(a[0]['估算期貨點位'], b[0]['估算期貨點位'])
    def test_breached_unreachable_invalid(self):
        self.assertEqual(thresholds(40000,1,500000,701000,538000,25)[0]['狀態'], '已達／低於門檻')
        self.assertIsNone(thresholds(100,1,1000000,701000,538000,25)[0]['估算期貨點位'])
        for price in [0, float('nan')]:
            with self.assertRaises(ValueError): thresholds(price,1,701000,701000,538000,25)
    def test_calculator_ui(self):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1]/'streamlit_app.py')).run()
        app.text_input(key='tx_price').set_value('43376')
        app.text_input(key='tx_original').set_value('701000')
        app.text_input(key='tx_maintenance').set_value('538000')
        next(b for b in app.button if b.label=='計算還可下跌幾點／幾％').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.dataframe[0].value.iloc[0]['估算期貨點位'],42561)
