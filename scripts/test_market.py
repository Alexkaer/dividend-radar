import unittest
from update_market import breadth, turnover_summary, sentiment

class MarketTests(unittest.TestCase):
    def test_breadth_excludes_missing_and_nonpositive_quotes(self):
        quotes={str(i):dict(f2=p,f3=v) for i,(p,v) in enumerate([(10,1),(10,-1),(10,0),(0,8),(10,None)])}
        result=breadth(quotes)
        self.assertEqual((result['up'],result['down'],result['flat'],result['total']),(1,1,1,3))
        self.assertEqual(result['advanceShare'],0.5)

    def test_volume_aligns_dates_and_compares_equal_windows(self):
        rows=[dict(date=f'2026-01-{i:02}',amount=100 if i<=5 else 200) for i in range(1,11)]
        result=turnover_summary(rows,list(reversed(rows)),'2026-01-10')
        self.assertEqual(result['today'],400)
        self.assertEqual(result['fiveDayChangePct'],100)
        self.assertEqual(result['dayChangePct'],0)
        with self.assertRaises(ValueError):turnover_summary(rows,rows[:-1],'2026-01-10')

    def test_sentiment_neutral_and_extreme_bounds(self):
        idx=[dict(code='000001',change=0),dict(code='399001',change=0)]
        self.assertEqual(sentiment(dict(advanceShare=.5),dict(up=10,down=10),idx)['score'],50)
        for r in idx:r['change']=20
        result=sentiment(dict(advanceShare=1),dict(up=100,down=0),idx)
        self.assertEqual(result['score'],100)
        self.assertEqual(result['label'],'活跃')
        self.assertIsNone(sentiment(dict(advanceShare=.5),dict(up=0,down=0),idx)['score'])

if __name__=='__main__':unittest.main()
