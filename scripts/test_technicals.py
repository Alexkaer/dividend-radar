import unittest
from datetime import date, timedelta
from technicals import boll, calculate, weekly_closes

class BollTests(unittest.TestCase):
    def test_known_population_bands_and_uptrend(self):
        bars=[(str(date(2026,1,1)+timedelta(days=i)),float(i+1)) for i in range(21)]
        result=boll(bars,'日')
        self.assertAlmostEqual(result['middle'],11.5)
        self.assertAlmostEqual(result['upper'],23.0326,places=4)
        self.assertEqual(result['trend'],'向上')
        self.assertEqual(result['position'],'日上')

    def test_flat_and_insufficient(self):
        self.assertIsNone(boll([('2026-01-01',10)]*20,'日'))
        result=boll([('2026-01-01',10)]*21,'周')
        self.assertEqual(result['position'],'周中')
        self.assertEqual(result['trend'],'走平')
        self.assertEqual(result['percentB'],0.5)

    def test_natural_week_uses_last_available_close(self):
        self.assertEqual(weekly_closes([('2026-10-30',10),('2026-11-02',11),('2026-11-03',12)]),[('2026-10-30',10),('2026-11-03',12)])

    def test_future_bars_excluded_and_stale_marked(self):
        result=calculate([('2026-11-02',10),('2026-11-04',20)],'2026-11-03')
        self.assertEqual(result['asOf'],'2026-11-02')
        self.assertEqual(result['status'],'incomplete')

    def test_invalid_prices_rejected(self):
        with self.assertRaises(ValueError): calculate([('2026-11-03',float('nan'))],'2026-11-03')

if __name__=='__main__': unittest.main()
